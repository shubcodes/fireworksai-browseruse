import asyncio
import os
import json
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.manus import Manus
from app.llm import LLM
from app.logger import logger
from app.schema import ToolCall, Message


class UserMessage(BaseModel):
    content: str


class OpenManusUI:
    """UI server for OpenManus."""

    def __init__(self, static_dir: Optional[str] = None):
        self.app = FastAPI(title="OpenManus UI")
        self.agent: Optional[Manus] = None
        self.active_websockets: List[WebSocket] = []
        self.frontend_dir = static_dir or os.path.join(os.path.dirname(__file__), "../../frontend/openmanus-ui/dist")

        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Set up routes
        self.setup_routes()

        # Mount static files if directory exists
        if os.path.exists(self.frontend_dir):
            self.app.mount("/", StaticFiles(directory=self.frontend_dir, html=True), name="static")

    def setup_routes(self):
        """Set up API routes."""

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.active_websockets.append(websocket)

            try:
                # Don't initialize agent on connection, only when a message is received
                # Send initial connection success
                await websocket.send_json({"type": "connect", "status": "success"})
                logger.info("Client connected via WebSocket")

                # Handle messages
                while True:
                    data = await websocket.receive_json()
                    logger.info(f"Received WebSocket message: {data}")

                    if "content" in data:
                        user_message = data["content"]
                        logger.info(f"Processing message: {user_message}")

                        # Initialize agent only if not already done
                        if self.agent is None:
                            self.agent = Manus()
                            self.patch_agent_methods()

                        # Process the message
                        asyncio.create_task(self.process_message(user_message))

            except WebSocketDisconnect:
                if websocket in self.active_websockets:
                    self.active_websockets.remove(websocket)
                logger.info("Client disconnected from WebSocket")

            except Exception as e:
                logger.error(f"WebSocket error: {str(e)}", exc_info=True)
                if websocket in self.active_websockets:
                    self.active_websockets.remove(websocket)

        @self.app.get("/api/status")
        async def get_status():
            """Check if the server is running."""
            return JSONResponse({
                "status": "online",
                "agent_initialized": self.agent is not None
            })

        @self.app.post("/api/message")
        async def post_message(message: UserMessage):
            """Alternative API endpoint for processing messages."""
            # Initialize agent if needed
            if self.agent is None:
                self.agent = Manus()
                self.patch_agent_methods()

            # Process the message in background
            asyncio.create_task(self.process_message(message.content))

            return JSONResponse({
                "status": "processing",
                "message": message.content
            })

        @self.app.get("/")
        async def get_index():
            """Serve the index.html file."""
            index_path = os.path.join(self.frontend_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"message": "Frontend not built yet. Please run 'npm run build' in the frontend directory."}

    async def broadcast_message(self, message_type: str, data: dict):
        """Broadcast a message to all connected WebSocket clients."""
        message = {"type": message_type, **data}

        # Add extra logging for browser state messages
        if message_type == "browser_state" and "base64_image" in data:
            image_data = data["base64_image"]
            logger.info(f"Broadcasting browser image: {len(image_data) if image_data else 0} bytes")

        for websocket in self.active_websockets:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to client: {str(e)}")
                # Remove broken connections
                if websocket in self.active_websockets:
                    self.active_websockets.remove(websocket)

    def patch_agent_methods(self):
        """Patch the agent methods to intercept and broadcast relevant information."""
        if not self.agent:
            return

        # Patch browser state method
        if hasattr(self.agent, "get_browser_state"):
            original_get_browser_state = self.agent.get_browser_state

            async def patched_get_browser_state(*args, **kwargs):
                result = await original_get_browser_state(*args, **kwargs)

                # If browser has a screenshot, broadcast it
                if hasattr(self.agent, "_current_base64_image") and self.agent._current_base64_image:
                    # Explicitly capture and send the screenshot to the UI
                    await self.broadcast_message("browser_state", {
                        "base64_image": self.agent._current_base64_image
                    })
                    logger.info("Browser screenshot captured and broadcasted")

                return result

            self.agent.get_browser_state = patched_get_browser_state

        # Patch think method
        if hasattr(self.agent, "think"):
            original_think = self.agent.think

            async def patched_think(*args, **kwargs):
                # Log thinking step
                await self.broadcast_message("agent_action", {
                    "action": "Agent Thinking",
                    "details": "Analyzing current state and deciding next actions..."
                })

                result = await original_think(*args, **kwargs)
                return result

            self.agent.think = patched_think

        # Patch execute_tool method
        if hasattr(self.agent, "execute_tool"):
            original_execute_tool = self.agent.execute_tool

            async def patched_execute_tool(command, *args, **kwargs):
                tool_name = command.function.name
                arguments = command.function.arguments

                # Log the tool execution
                await self.broadcast_message("agent_action", {
                    "action": f"Tool: {tool_name}",
                    "details": f"Arguments: {arguments}"
                })

                # Special handling for browser_use tool
                is_browser_tool = tool_name in ["browser_use", "browser"]

                # Execute the tool
                result = await original_execute_tool(command, *args, **kwargs)

                # Special handling for browser screenshots
                if is_browser_tool and result:
                    # Try to extract the screenshot if it exists
                    try:
                        # Try various ways to find the screenshot
                        if hasattr(result, "base64_image") and result.base64_image:
                            await self.broadcast_message("browser_state", {
                                "base64_image": result.base64_image
                            })
                            logger.info(f"Screenshot captured from tool result")
                        elif hasattr(self.agent, "_current_base64_image") and self.agent._current_base64_image:
                            await self.broadcast_message("browser_state", {
                                "base64_image": self.agent._current_base64_image
                            })
                            logger.info(f"Screenshot captured from agent")

                        # Inspect result object more deeply
                        logger.info(f"Browser tool result type: {type(result)}")
                        if hasattr(result, "__dict__"):
                            logger.info(f"Browser tool result attributes: {result.__dict__.keys()}")
                            # Log if there are any image-like attributes
                            for key, value in result.__dict__.items():
                                if isinstance(value, str) and len(value) > 1000 and 'base64' in key.lower():
                                    logger.info(f"Found potential image in attribute: {key}")
                                    await self.broadcast_message("browser_state", {
                                        "base64_image": value
                                    })

                        # Check if result has a model_dump method (Pydantic)
                        if hasattr(result, "model_dump"):
                            result_dict = result.model_dump()
                            for key, value in result_dict.items():
                                if isinstance(value, str) and len(value) > 1000 and ('image' in key.lower() or 'base64' in key.lower()):
                                    logger.info(f"Found potential image in model_dump(): {key}")
                                    await self.broadcast_message("browser_state", {
                                        "base64_image": value
                                    })
                    except Exception as e:
                        logger.error(f"Error capturing screenshot: {e}")

                # Log the result
                await self.broadcast_message("agent_action", {
                    "action": f"Result: {tool_name}",
                    "details": str(result)
                })

                return result

            self.agent.execute_tool = patched_execute_tool

        # Also patch the browser tool's get_current_state method
        browser_tool = None
        if hasattr(self.agent, "available_tools") and hasattr(self.agent.available_tools, "get_tool"):
            for tool_name in ["browser_use", "browser"]:
                browser_tool = self.agent.available_tools.get_tool(tool_name)
                if browser_tool:
                    logger.info(f"Found browser tool: {tool_name}")
                    # List all methods to help with debugging
                    tool_methods = [method for method in dir(browser_tool) if not method.startswith('_')]
                    logger.info(f"Available methods: {tool_methods}")
                    break

        if browser_tool:
            # Add a callback function that will be called when screenshots are captured
            async def screenshot_callback(base64_image):
                if base64_image:
                    await self.broadcast_message("browser_state", {
                        "base64_image": base64_image
                    })
                    logger.info(f"Screenshot captured and broadcasted: {len(base64_image)} bytes")

            # Store the callback in the browser tool instance so it persists
            browser_tool._ui_screenshot_callback = screenshot_callback

            # Patch the agent's get_browser_state method instead
            if hasattr(self.agent, "get_browser_state"):
                original_agent_get_browser_state = self.agent.get_browser_state

                async def patched_agent_get_browser_state(*args, **kwargs):
                    result = await original_agent_get_browser_state(*args, **kwargs)

                    # If browser has a screenshot, broadcast it
                    if hasattr(self.agent, "_current_base64_image") and self.agent._current_base64_image:
                        await self.broadcast_message("browser_state", {
                            "base64_image": self.agent._current_base64_image
                        })
                        logger.info(f"Agent screenshot captured and broadcasted: {len(self.agent._current_base64_image)} bytes")

                    return result

                self.agent.get_browser_state = patched_agent_get_browser_state

        # Patch the message memory to intercept image messages
        memory = None
        if hasattr(self.agent, "memory"):
            memory = self.agent.memory
            # Log memory methods for debugging
            memory_methods = [method for method in dir(memory) if not method.startswith('_')]
            logger.info(f"Memory methods: {memory_methods}")

            # Check if memory has add_message method
            if "add_message" in memory_methods:
                try:
                    # Try to get the original method correctly
                    original_add_message = memory.add_message

                    # Define a new method that captures images
                    async def patched_add_message(message, *args, **kwargs):
                        # If the message has an image, broadcast it
                        if hasattr(message, "base64_image") and message.base64_image:
                            await self.broadcast_message("browser_state", {
                                "base64_image": message.base64_image
                            })
                            logger.info(f"Image message captured and broadcasted: {len(message.base64_image)} bytes")

                        # Call the original method
                        if asyncio.iscoroutinefunction(original_add_message):
                            return await original_add_message(message, *args, **kwargs)
                        else:
                            return original_add_message(message, *args, **kwargs)

                    # Replace the original method
                    memory.add_message = patched_add_message
                    logger.info("Successfully patched memory.add_message")
                except AttributeError as e_attr:
                    logger.error(f"Failed to patch memory.add_message due to AttributeError: {e_attr}. The 'Memory' object might not be what was expected at this point.")
                except Exception as e_gen:
                    logger.error(f"An unexpected error occurred while patching memory.add_message: {e_gen}")
            else:
                logger.warning("Memory has no add_message method to patch")

    async def process_message(self, message: str):
        """Process a user message with the agent and broadcast results."""
        try:
            if not self.agent:
                self.agent = Manus()
                self.patch_agent_methods()

            # Don't immediately launch browser - wait for explicit action
            # Ensure agent knows the message
            await self.broadcast_message("agent_action", {
                "action": "Processing Request",
                "details": f"Analyzing: {message}"
            })

            # Add a timeout mechanism to prevent infinite loops
            # This prevents the agent from endlessly repeating steps without sending a final response
            max_steps = 10  # Set this to a reasonable number of steps
            max_execution_time = 60  # Maximum execution time in seconds

            # Run the agent with the user's message and a timeout
            try:
                # Use asyncio.wait_for to set a timeout
                response = await asyncio.wait_for(
                    self.agent.run(message),
                    timeout=max_execution_time
                )
            except asyncio.TimeoutError:
                logger.warning(f"Agent execution timed out after {max_execution_time} seconds")
                # Even if we timeout, we can still extract thoughts/content from memory
                response = "Agent execution timed out, but findings are still available."

            logger.info(f"Raw agent response: {response[:100]}...") # Add logging to see raw response

            # Extract the final result intended for the user
            final_agent_output = self.agent._final_result if hasattr(self.agent, '_final_result') and self.agent._final_result else response

            logger.info(f"Final agent output: {final_agent_output[:100]}...") # Add logging to see final_agent_output

            # Check if agent has memory and look for extraction content in recent messages
            extracted_content = None
            agent_thoughts = None
            if hasattr(self.agent, "memory") and hasattr(self.agent.memory, "messages"):
                recent_msgs = self.agent.memory.messages[-10:] # Get 10 most recent messages
                logger.info(f"Recent message count: {len(recent_msgs)}")

                # First, look for agent's thoughts
                for msg in reversed(recent_msgs):
                    if hasattr(msg, "content") and msg.content and isinstance(msg.content, str):
                        # Check if this is an agent thought message
                        if "Manus's thoughts:" in msg.content or "thoughts:" in msg.content:
                            logger.info(f"Found agent thoughts: {msg.content[:100]}...")
                            agent_thoughts = msg.content
                            # If thoughts include a recommendation or answer, use it as the final output
                            break

                # Then check for extraction results if no thoughts found
                if not agent_thoughts:
                    for msg in reversed(recent_msgs):
                        if hasattr(msg, "content") and msg.content and isinstance(msg.content, str):
                            if "Extracted from page:" in msg.content:
                                logger.info(f"Found extraction in recent message: {msg.content[:100]}...")
                                extracted_content = msg.content
                                break

            # If we found agent thoughts, prioritize these as they contain the agent's reasoning
            if agent_thoughts:
                logger.info("Using agent thoughts as final output")
                final_agent_output = agent_thoughts
                # Extract just the response part from thoughts, removing the "Manus's thoughts:" prefix
                if "✨ Manus's thoughts:" in agent_thoughts:
                    cleaned_thoughts = agent_thoughts.split("✨ Manus's thoughts:", 1)[1].strip()
                    # Use this as the direct answer
                    await self.broadcast_message("agent_message", {
                        "content": cleaned_thoughts
                    })
                    logger.info("Successfully sent agent thoughts to client")

                    # Force terminate the agent to prevent further execution loops
                    if hasattr(self.agent, "state"):
                        try:
                            logger.info("Setting agent state to FINISHED to stop further execution")
                            self.agent.state = "FINISHED"
                        except Exception as term_e:
                            logger.error(f"Error terminating agent: {term_e}")

                    return
            # If we found an extraction result, use it instead of raw final_agent_output
            elif extracted_content:
                logger.info("Using extracted content instead of final agent output")
                final_agent_output = extracted_content

            # --- New Formatting Logic ---
            needs_formatting = False
            extracted_text_for_prompt = None # Initialize variable to hold the text for the prompt

            if isinstance(final_agent_output, str):
                 # Try to find and parse the JSON within "Extracted from page:"
                 extraction_marker = "Extracted from page:"
                 if extraction_marker in final_agent_output:
                     try:
                         # Find the start of the JSON object after the marker
                         json_part = final_agent_output.split(extraction_marker, 1)[1].strip()
                         logger.info(f"Attempting to parse JSON from: >>>{json_part}<<<" )
                         data = json.loads(json_part)
                         logger.info(f"Parsed JSON data type: {type(data)}")
                         if isinstance(data, dict):
                             logger.info(f"Parsed JSON data keys: {list(data.keys())}")

                         if isinstance(data, dict) and 'text' in data:
                             extracted_text_for_prompt = data['text']
                             needs_formatting = True
                             logger.info("Found extracted text in JSON format - IMMEDIATE FORMATTING")
                             # Immediately format and send the answer rather than continuing
                             try:
                                 logger.info(f"Immediate formatting response using Maverick model for user query: {message}")
                                 logger.info(f"Extracted text for prompt: {extracted_text_for_prompt}")

                                 # Create a dedicated LLM instance for formatting using the Maverick model
                                 formatter_llm = LLM(model_name="accounts/fireworks/models/llama4-maverick-instruct-basic")

                                 # Prepare the prompt for the formatting model
                                 format_prompt = f"""Given the user's question and the information found by an agent, provide a natural, conversational answer. Focus only on the information relevant to the question.

Original User Question:
{message}

Information Found:
{extracted_text_for_prompt}

Answer:"""

                                 logger.info(f"Sending immediate format prompt to Maverick: {format_prompt[:150]}...")

                                 # Call the formatting LLM (non-streaming for a complete answer)
                                 formatted_response = await formatter_llm.ask(
                                     messages=[Message.user_message(format_prompt)],
                                     system_msgs=[Message.system_message("You are an assistant that rephrases technical agent output into a natural, conversational response based *only* on the provided findings. Be concise and directly answer the user's question using the information.")],
                                     stream=False, # Get the full response at once
                                     temperature=0.6 # Use the specified temperature
                                 )

                                 # Log and broadcast the formatted response
                                 logger.info(f"✅ IMMEDIATE formatted response using Maverick: {formatted_response}")
                                 await self.broadcast_message("agent_message", {
                                     "content": formatted_response
                                 })
                                 logger.info("✅ Successfully sent immediate formatted response to client")

                                 # Ensure we don't send the unformatted response later
                                 self.agent._final_result = formatted_response # Update the final result to prevent double sending

                                 # Force terminate the agent to prevent further execution loops
                                 if hasattr(self.agent, "state"):
                                     try:
                                         logger.info("Setting agent state to FINISHED to stop further execution")
                                         self.agent.state = "FINISHED"
                                     except Exception as term_e:
                                         logger.error(f"Error terminating agent: {term_e}")

                                 return # Exit after successful formatting and broadcast

                             except Exception as e:
                                 logger.error(f"Error during immediate formatting with Maverick LLM: {str(e)}", exc_info=True)
                                 # Continue with normal flow if immediate formatting fails
                         else:
                             logger.warning("Found extraction marker but failed to get text from JSON.")
                     except Exception as json_e:
                         logger.warning(f"Error parsing JSON after extraction marker: {json_e}")
                         # Fallback: Check if the raw output itself might need formatting based on keywords
                         if 'Searched for' in final_agent_output or 'Navigated to' in final_agent_output:
                              needs_formatting = True
                              extracted_text_for_prompt = final_agent_output # Use the raw output

            if needs_formatting and extracted_text_for_prompt:
                try:
                    logger.info(f"Formatting final response using Maverick model for user query: {message}")
                    logger.info(f"Extracted text for prompt: {extracted_text_for_prompt}")

                    # Create a dedicated LLM instance for formatting using the Maverick model
                    formatter_llm = LLM(model_name="accounts/fireworks/models/llama4-maverick-instruct-basic")

                    # Prepare the prompt for the formatting model
                    format_prompt = f"""Given the user's question and the information found by an agent, provide a natural, conversational answer. Focus only on the information relevant to the question.

Original User Question:
{message}

Information Found:
{extracted_text_for_prompt}

Answer:"""

                    logger.info(f"Sending format prompt to Maverick: {format_prompt[:150]}...")

                    # Call the formatting LLM (non-streaming for a complete answer)
                    formatted_response = await formatter_llm.ask(
                        messages=[Message.user_message(format_prompt)],
                        system_msgs=[Message.system_message("You are an assistant that rephrases technical agent output into a natural, conversational response based *only* on the provided findings. Be concise and directly answer the user's question using the information.")],
                        stream=False, # Get the full response at once
                        temperature=0.6 # Use the specified temperature
                    )

                    # Log and broadcast the formatted response
                    logger.info(f"✅ Formatted response using Maverick: {formatted_response}")
                    await self.broadcast_message("agent_message", {
                        "content": formatted_response
                    })
                    logger.info("✅ Successfully sent formatted response to client")

                    # Ensure we don't send the unformatted response later
                    self.agent._final_result = formatted_response # Update the final result to prevent double sending
                    return # Exit after successful formatting and broadcast

                except Exception as e:
                    logger.error(f"Error formatting response with Maverick LLM: {str(e)}", exc_info=True)
                    # Fallback: Send the potentially unformatted final_agent_output if formatting fails
                    logger.info("Falling back to unformatted output")
                    final_content = final_agent_output # Use the original agent output as fallback
            else:
                 # If no formatting was deemed necessary, use the agent's output directly
                 logger.info("No formatting needed, using agent output directly")
                 final_content = final_agent_output

            # Final broadcast if formatting wasn't needed or failed
            # Clean up potential raw tool output remnants like "Observed output..." just in case
            if isinstance(final_content, str) and "Observed output of cmd" in final_content:
                 final_content = final_content.split("\\\\n", 1)[1] if "\\\\n" in final_content else final_content

            await self.broadcast_message("agent_message", {
                 "content": final_content
            })

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.broadcast_message("agent_message", {
                "content": f"Error: {str(e)}"
            })

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the UI server."""
        logger.info(f"Starting OpenManus UI server at http://{host}:{port}")
        uvicorn.run(self.app, host=host, port=port)


# Entry point to run the server directly
if __name__ == "__main__":
    ui_server = OpenManusUI()
    ui_server.run()
