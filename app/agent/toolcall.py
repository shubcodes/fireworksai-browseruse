import json
from typing import Any, List, Optional, Union, Dict

from pydantic import Field

from app.llm import LLM
from app.agent.base import BaseAgent
from app.agent.react import ReActAgent
from app.logger import logger
from app.prompt.toolcall import NEXT_STEP_PROMPT, SYSTEM_PROMPT
from app.schema import TOOL_CHOICE_TYPE, AgentState, Message, ToolCall, ToolChoice
from app.tool import CreateChatCompletion, Terminate, ToolCollection
from app.tool.base import ToolResult

TOOL_CALL_REQUIRED = "Tool calls required but none provided"

class TerminateToolError(Exception):
    """Custom exception for errors specifically from the Terminate tool."""
    pass

class ToolCallAgent(ReActAgent):
    """Base agent class for handling tool/function calls with enhanced abstraction"""

    name: str = "toolcall"
    description: str = "an agent that can execute tool calls."

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = ToolCollection(
        CreateChatCompletion(), Terminate()
    )
    tool_choices: TOOL_CHOICE_TYPE = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    tool_calls: List[ToolCall] = Field(default_factory=list)
    _current_base64_image: Optional[str] = None
    _final_result: Optional[str] = None  # Store the final result before termination
    extraction_attempts: Dict[str, int] = Field(default_factory=dict)  # Track extraction attempts per URL
    last_extraction_url: Optional[str] = None  # Track the last URL we tried to extract from

    max_steps: int = 30
    max_observe: Optional[Union[int, bool]] = None
    max_extraction_attempts: int = 3  # Maximum attempts to extract content from the same page

    async def think(self) -> bool:
        """Process current state and decide next actions using tools"""
        if self.next_step_prompt:
            user_msg = Message.user_message(self.next_step_prompt)
            self.messages += [user_msg]

        try:
            # Get response with tool options
            response = await self.llm.ask_tool(
                messages=self.messages,
                system_msgs=(
                    [Message.system_message(self.system_prompt)]
                    if self.system_prompt
                    else None
                ),
                tools=self.available_tools.to_params(),
                tool_choice=self.tool_choices,
            )
        except ValueError:
            raise
        except Exception as e:
            # Check if this is a RetryError containing TokenLimitExceeded
            if hasattr(e, "__cause__") and isinstance(e.__cause__, TokenLimitExceeded):
                token_limit_error = e.__cause__
                logger.error(
                    f"🚨 Token limit error (from RetryError): {token_limit_error}"
                )
                self.memory.add_message(
                    Message.assistant_message(
                        f"Maximum token limit reached, cannot continue execution: {str(token_limit_error)}"
                    )
                )
                self.state = AgentState.FINISHED
                return False
            raise

        self.tool_calls = tool_calls = (
            response.tool_calls if response and response.tool_calls else []
        )
        content = response.content if response and response.content else ""

        # Log response info
        logger.info(f"✨ {self.name}'s thoughts: {content}")
        logger.info(
            f"🛠️ {self.name} selected {len(tool_calls) if tool_calls else 0} tools to use"
        )
        if tool_calls:
            logger.info(
                f"🧰 Tools being prepared: {[call.function.name for call in tool_calls]}"
            )
            logger.info(f"🔧 Tool arguments: {tool_calls[0].function.arguments}")

        try:
            if response is None:
                raise RuntimeError("No response received from the LLM")

            # Handle different tool_choices modes
            if self.tool_choices == ToolChoice.NONE:
                if tool_calls:
                    logger.warning(
                        f"🤔 Hmm, {self.name} tried to use tools when they weren't available!"
                    )
                if content:
                    self.memory.add_message(Message.assistant_message(content))
                    return True
                return False

            # Create and add assistant message
            assistant_msg = (
                Message.from_tool_calls(content=content, tool_calls=self.tool_calls)
                if self.tool_calls
                else Message.assistant_message(content)
            )
            self.memory.add_message(assistant_msg)

            # Check if we have gathered enough information and should terminate
            if content and "Final Summary:" in content:
                # Store the final result before terminating
                self._final_result = content
                # Call terminate tool
                terminate_tool_call = ToolCall(
                    id="terminate",
                    type="function",
                    function={"name": "terminate", "arguments": "{}"}
                )
                self.tool_calls = [terminate_tool_call]
                return True

            if self.tool_choices == ToolChoice.REQUIRED and not self.tool_calls:
                return True  # Will be handled in act()

            # For 'auto' mode, continue with content if no commands but content exists
            if self.tool_choices == ToolChoice.AUTO and not self.tool_calls:
                return bool(content)

            return bool(self.tool_calls)
        except Exception as e:
            logger.error(f"🚨 Oops! The {self.name}'s thinking process hit a snag: {e}")
            self.memory.add_message(
                Message.assistant_message(
                    f"Error encountered while processing: {str(e)}"
                )
            )
            return False

    async def act(self) -> str:
        """Execute tool calls and handle their results"""
        if not self.tool_calls:
            if self.tool_choices == ToolChoice.REQUIRED:
                raise ValueError(TOOL_CALL_REQUIRED)

            # Return last message content if no tool calls
            return self.messages[-1].content or "No content or commands to execute"

        results = []
        for command in self.tool_calls:
            # Check if the agent has been terminated by a previous tool call in this loop
            if self.state == AgentState.FINISHED:
                logger.info("Agent state is FINISHED, stopping further tool execution in this step.")
                break

            # Reset base64_image for each tool call
            self._current_base64_image = None

            result, terminated = await self.execute_tool(command)

            if self.max_observe:
                result = result[: self.max_observe]

            logger.info(
                f"🎯 Tool '{command.function.name}' completed its mission! Result: {result}"
            )

            # Add tool response to memory
            tool_msg = Message.tool_message(
                content=result,
                tool_call_id=command.id,
                name=command.function.name,
                base64_image=self._current_base64_image,
            )
            self.memory.add_message(tool_msg)
            results.append(result)

            # Check if this tool call resulted in termination
            if terminated:
                logger.info(f"Agent terminated by tool '{command.function.name}'. Stopping further actions in this step.")
                break # Stop processing further tool calls in this step

        return "\n\n".join(results)

    async def execute_tool(self, command: ToolCall) -> tuple[str, bool]:
        """Execute a tool and handle the result. Returns (result_string, terminated_bool)."""
        terminated = False # Initialize termination flag
        try:
            name = command.function.name
            args = command.function.arguments
            logger.info(f"🔧 Activating tool: '{name}'...")

            # Parse args as a dict
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, Exception):
                    args = {}

            # Extract tool result
            tool_result = await self.available_tools.execute(name=name, tool_input=args)

            # Handle tool exceptions and convert to string
            if isinstance(tool_result, Exception):
                result = str(tool_result)
            elif isinstance(tool_result, ToolResult):
                result = str(tool_result)
                # Capture screenshot if available in ToolResult
                if hasattr(tool_result, "base64_image") and tool_result.base64_image:
                     self._current_base64_image = tool_result.base64_image
            else:
                result = str(tool_result) if tool_result is not None else ""

            # Handle special tools (like terminate)
            # Note: _handle_special_tool sets self.state = AgentState.FINISHED
            await self._handle_special_tool(name=name, result=result)
            if self.state == AgentState.FINISHED:
                terminated = True
                # If terminating, ensure the final_result reflects the termination message or prior useful data
                if name.lower() == "terminate":
                    # Use the result from the terminate tool itself
                     self._final_result = result
                # else: Keep the existing _final_result (likely the data found before termination)

            # For browser_use tool, update tracking and store result
            if name == "browser_use" and isinstance(result, str):
                # Store the result from browser actions (extraction, navigation etc.)
                # The server-side formatting logic will handle this later
                self._final_result = result

                # Track extraction attempts for this URL if it's an extraction action
                if args.get("action") == "extract_content" and isinstance(args.get("goal"), str):
                    current_url = self.last_extraction_url
                    extraction_goal = args.get("goal", "").lower()
                    if current_url:
                        extraction_key = f"{current_url}:{extraction_goal}"
                        self.extraction_attempts[extraction_key] = self.extraction_attempts.get(extraction_key, 0) + 1
                        if self.extraction_attempts[extraction_key] >= self.max_extraction_attempts:
                            logger.warning(f"Reached maximum extraction attempts ({self.max_extraction_attempts}) for {extraction_key}")
                            # If we still couldn't extract, try a generic extraction as a last resort
                            if "not available" in result.lower() or "Error occurred during extraction" in result:
                                logger.info("Final attempt with generic extraction after max attempts.")
                                try:
                                    generic_args = {"action": "extract_content", "goal": "Extract all important information on this page"}
                                    follow_up_result_obj = await self.available_tools.execute(name="browser_use", tool_input=generic_args)
                                    follow_up_result = str(follow_up_result_obj) # Convert to string
                                    if follow_up_result and "not available" not in follow_up_result.lower() and "Error occurred" not in follow_up_result:
                                        logger.info("Found better result with generic extraction")
                                        self._final_result = follow_up_result
                                        result = follow_up_result # Update the result for this step
                                        # Capture screenshot if the fallback result has one
                                        if isinstance(follow_up_result_obj, ToolResult) and follow_up_result_obj.base64_image:
                                            self._current_base64_image = follow_up_result_obj.base64_image
                                except Exception as e:
                                    logger.error(f"Error in follow-up generic extraction: {e}")
                            # Note: Automatic termination logic removed here, rely on agent's next thought or max_steps

                # Update URL tracking for navigation actions
                elif args.get("action") == "go_to_url" and isinstance(args.get("url"), str):
                    self.last_extraction_url = args.get("url")
                    self.extraction_attempts = {} # Reset attempts on navigation
                elif args.get("action") == "web_search":
                    # Extract the navigated URL from the web search result string
                    search_result_lines = result.split('\\n')
                    if search_result_lines and "navigated to first result:" in search_result_lines[0]:
                         try:
                            self.last_extraction_url = search_result_lines[0].split("navigated to first result: ")[1].strip()
                         except IndexError:
                             self.last_extraction_url = None # Failed to parse URL
                    else:
                         self.last_extraction_url = None # Navigated to search results page, not a specific link
                    self.extraction_attempts = {} # Reset attempts on navigation

            # Log the result to agent memory (this now happens in act loop)
            # verbose_output = f"Observed output of cmd `{name}` executed:\\n{str(result)}"
            # self.memory.add_message(Message.system_message(verbose_output))

            return result, terminated

        except Exception as e:
            # Handle any uncaught exceptions during tool execution
            try:
                # Try to get tool name for context, might fail if error happened before 'name' assignment
                error_context_name = name if 'name' in locals() else 'unknown tool'
                error_msg = f"⚠️ Tool '{error_context_name}' encountered a problem: {str(e)}"
            except Exception: # Fallback if even getting the name fails
                error_msg = f"⚠️ Tool execution encountered a problem: {str(e)}"
            logger.exception(error_msg)
            return f"Error: {error_msg}", False # Return error message and False for terminated flag

    async def _handle_special_tool(self, name: str, result: Any, **kwargs):
        """Handle special tool execution and state changes"""
        if not self._is_special_tool(name):
            return

        if self._should_finish_execution(name=name, result=result, **kwargs):
            # Set agent state to finished
            logger.info(f"🏁 Special tool '{name}' has completed the task!")
            self.state = AgentState.FINISHED

    @staticmethod
    def _should_finish_execution(**kwargs) -> bool:
        """Determine if tool execution should finish the agent"""
        return True

    def _is_special_tool(self, name: str) -> bool:
        """Check if tool name is in special tools list"""
        return name.lower() in [n.lower() for n in self.special_tool_names]
