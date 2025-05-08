import { useState, useEffect, useRef } from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import {
  Box,
  Typography,
  TextField,
  Button,
  Paper,
  Toolbar,
  Tabs,
  Tab,
  Avatar,
  useTheme
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import SendIcon from '@mui/icons-material/Send';
import OpenInFullIcon from '@mui/icons-material/OpenInFull';
import CloseIcon from '@mui/icons-material/Close';
import './App.css';

// Define types for our application
type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
};

type AgentAction = {
  action: string;
  details: string;
  timestamp: number;
};

function App() {
  const theme = useTheme();
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [agentActions, setAgentActions] = useState<AgentAction[]>([]);
  const [browserState, setBrowserState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [streamingMessage, setStreamingMessage] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);
  const browserEndRef = useRef<HTMLDivElement>(null);

  // Connect to WebSocket server when component mounts
  useEffect(() => {
    // Create WebSocket connection
    // In development, connect directly to the backend
    const socketUrl = 'ws://localhost:8000/ws';

    console.log('Connecting to WebSocket at:', socketUrl);

    const newSocket = new WebSocket(socketUrl);

    newSocket.onopen = () => {
      console.log('WebSocket connection established');
      setConnected(true);
    };

    newSocket.onclose = () => {
      console.log('WebSocket connection closed');
      setConnected(false);
    };

    newSocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    newSocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('Received message:', data);

      if (data.type === 'connect') {
        console.log('Connection confirmed by server');
      } else if (data.type === 'agent_message') {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: data.content,
          timestamp: Date.now()
        }]);
        setIsLoading(false);
        // Switch to chat tab when receiving messages
        setActiveTab(0);
      } else if (data.type === 'agent_message_stream_start') {
        // Initialize streaming state
        setIsStreaming(true);
        setStreamingMessage('');
        // Add an empty message that will be updated
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '',
          timestamp: Date.now()
        }]);
        setActiveTab(0);
      } else if (data.type === 'agent_message_stream_chunk') {
        // Update the streaming message with new chunk
        setStreamingMessage(prev => prev + data.content);
        // Update the last message with current accumulated text
        setMessages(prev => {
          const newMessages = [...prev];
          if (newMessages.length > 0) {
            newMessages[newMessages.length - 1] = {
              ...newMessages[newMessages.length - 1],
              content: newMessages[newMessages.length - 1].content + data.content
            };
          }
          return newMessages;
        });
      } else if (data.type === 'agent_message_stream_end') {
        // Finalize streaming
        setIsStreaming(false);
        setIsLoading(false);
      } else if (data.type === 'agent_action') {
        setAgentActions(prev => [...prev, {
          action: data.action,
          details: data.details,
          timestamp: Date.now()
        }]);
      } else if (data.type === 'browser_state') {
        console.log('Received browser state with image data length:',
          data.base64_image ? data.base64_image.length : 0);

        if (data.base64_image && data.base64_image.length > 0) {
          setBrowserState(data.base64_image);
        } else {
          console.warn('Received empty browser screenshot');
        }
      }
    };

    setSocket(newSocket);

    // Cleanup on unmount
    return () => {
      newSocket.close();
    };
  }, []);

  // Auto-scroll chat and action logs to bottom when new content arrives
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    actionsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentActions]);

  // Remove auto-scroll for browser view
  useEffect(() => {
    // Only update state, don't auto-scroll
  }, [browserState]);

  // Handle sending messages
  const sendMessage = () => {
    if (!input.trim()) return;

    const newMessage: ChatMessage = {
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, newMessage]);

    // Try to send via WebSocket if connected
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log('Sending message via WebSocket:', input);
      socket.send(JSON.stringify({ content: input }));
    } else {
      // Fallback to HTTP API
      console.log('Sending message via HTTP API:', input);
      fetch('/api/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: input })
      })
        .then(response => response.json())
        .then(data => {
          console.log('API response:', data);
        })
        .catch(error => {
          console.error('Error sending message:', error);
        });
    }

    setInput('');
    setIsLoading(true);
  };

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  return (
    <Box
      sx={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: `linear-gradient(135deg, ${alpha(theme.palette.background.default, 0.7)} 0%, ${alpha(theme.palette.background.default, 0.9)} 100%)`,
        p: 1.5,
        gap: 1,
        overflow: 'hidden'
      }}
    >
      {/* Header Bubble */}
      <Paper
        elevation={0}
        className="glass-effect"
        sx={{
          borderRadius: 2,
          overflow: 'hidden',
          mb: 1,
          flexShrink: 0
        }}
      >
        <Toolbar sx={{ px: 3, minHeight: '56px' }}>
          <Avatar
            src="https://avatars.githubusercontent.com/u/114557877?s=280&v=4"
            alt="Fireworks"
            sx={{ width: 32, height: 32, mr: 1.5 }}
          />
          <Typography variant="h6" fontWeight="600">Fireworks Manus</Typography>
          <Box sx={{
            ml: 2,
            px: 1.5,
            py: 0.5,
            borderRadius: 10,
            backgroundColor: connected ? 'rgba(46, 196, 72, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            border: connected ? '1px solid rgba(46, 196, 72, 0.4)' : '1px solid rgba(239, 68, 68, 0.4)'
          }}>
            <Typography
              variant="caption"
              color={connected ? theme.palette.success.main : theme.palette.error.main}
              fontWeight="600"
            >
              {connected ? 'Connected' : 'Disconnected'}
            </Typography>
          </Box>
        </Toolbar>
      </Paper>

      {/* Main Content Area */}
      <Box sx={{ flexGrow: 1, overflow: 'hidden', display: 'flex', gap: 0 }}>
        <PanelGroup direction="horizontal" autoSaveId="panel-group-settings">
          {/* Left Panel - Chat Interface and Agent Activity */}
          <Panel defaultSize={40} minSize={30}>
            <Paper
              elevation={0}
              className="glass-effect"
              sx={{
                height: '100%',
                borderRadius: 2,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                mr: 0.25
              }}
            >
              {/* Tabs */}
              <Box sx={{
                borderBottom: 1,
                borderColor: 'divider',
                backgroundColor: alpha(theme.palette.background.paper, 0.6),
                flexShrink: 0 // Prevent tabs from shrinking
              }}>
                <Tabs
                  value={activeTab}
                  onChange={handleTabChange}
                  variant="fullWidth"
                  sx={{
                    '& .MuiTab-root': {
                      textTransform: 'none',
                      fontWeight: 500,
                      fontSize: '0.9rem'
                    },
                    '& .Mui-selected': {
                      color: theme.palette.primary.main
                    },
                    '& .MuiTabs-indicator': {
                      backgroundColor: theme.palette.primary.main
                    }
                  }}
                >
                  <Tab label="Chat" />
                  <Tab label="Agent Activity" />
                </Tabs>
              </Box>

              {/* Chat Interface */}
              <Box
                sx={{
                  display: activeTab === 0 ? 'flex' : 'none',
                  flexDirection: 'column',
                  flexGrow: 1
                }}
              >
                {/* Messages container */}
                <Box
                  sx={{
                    flexGrow: 1,
                    overflow: 'auto',
                    p: 2,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                    backgroundColor: alpha(theme.palette.background.default, 0.3),
                    height: 0, // Ensure container uses flex sizing to enable scrolling
                    minHeight: 0
                  }}
                  className="bubble-container"
                >
                  {messages.map((msg, index) => (
                    <Box
                      key={index}
                      sx={{
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '90%'
                      }}
                      className="fade-in"
                    >
                      <Paper
                        elevation={0}
                        className={msg.role === 'user' ? 'bubble bubble-user' : 'bubble bubble-assistant'}
                        sx={{
                          p: 2,
                          boxShadow: msg.role === 'user'
                            ? '0 2px 8px rgba(10, 132, 255, 0.25)'
                            : '0 2px 8px rgba(0, 0, 0, 0.15)',
                        }}
                      >
                        <Typography variant="body1" whiteSpace="pre-wrap">
                          {msg.content}
                        </Typography>
                      </Paper>
                    </Box>
                  ))}
                  {isLoading && (
                    <Box sx={{ alignSelf: 'flex-start', maxWidth: '90%' }} className="fade-in">
                      <Paper
                        elevation={0}
                        className="bubble bubble-assistant"
                        sx={{
                          p: 2,
                          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
                        }}
                      >
                        <Typography variant="body1">Thinking...</Typography>
                      </Paper>
                    </Box>
                  )}
                  <div ref={messagesEndRef} />
                </Box>

                {/* Input area */}
                <Box sx={{
                  p: 2,
                  backgroundColor: alpha(theme.palette.background.paper, 0.3),
                  backdropFilter: 'blur(10px)',
                  flexShrink: 0 // Prevent input area from shrinking
                }}>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth
                      variant="outlined"
                      placeholder="Type your message..."
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                      disabled={isLoading}
                      size="small"
                      sx={{
                        '& .MuiOutlinedInput-root': {
                          borderRadius: 3,
                          backgroundColor: alpha(theme.palette.background.paper, 0.5)
                        }
                      }}
                    />
                    <Button
                      variant="contained"
                      color="primary"
                      endIcon={<SendIcon />}
                      onClick={sendMessage}
                      disabled={!input.trim() || isLoading}
                      className="apple-button"
                      sx={{
                        borderRadius: 3,
                        textTransform: 'none'
                      }}
                    >
                      Send
                    </Button>
                  </Box>
                </Box>
              </Box>

              {/* Agent Activity Log */}
              <Box
                sx={{
                  display: activeTab === 1 ? 'flex' : 'none',
                  flexGrow: 1,
                  overflow: 'auto',
                  flexDirection: 'column',
                  p: 2,
                  gap: 1,
                  backgroundColor: alpha(theme.palette.background.default, 0.3),
                  height: 0, // Ensure container uses flex sizing to enable scrolling
                  minHeight: 0
                }}
                className="bubble-container"
              >
                <Typography
                  variant="subtitle2"
                  sx={{
                    mb: 1,
                    color: theme.palette.text.secondary,
                    fontWeight: 500
                  }}
                >
                  Tool and Action History
                </Typography>

                {agentActions.map((action, index) => (
                  <Paper
                    key={index}
                    elevation={0}
                    className="bubble bubble-assistant fade-in"
                    sx={{
                      p: 2,
                      mb: 1,
                      borderLeft: '4px solid',
                      borderColor: 'primary.main',
                      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
                      maxWidth: '95%'
                    }}
                  >
                    <Typography variant="subtitle2" fontWeight="bold">
                      {action.action}
                    </Typography>
                    <Typography
                      variant="body2"
                      component="pre"
                      sx={{
                        mt: 1,
                        p: 1,
                        bgcolor: alpha(theme.palette.background.default, 0.3),
                        borderRadius: 2,
                        overflow: 'auto',
                        fontSize: '0.85rem',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word'
                      }}
                    >
                      {action.details}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: 'block', mt: 1, textAlign: 'right' }}
                    >
                      {new Date(action.timestamp).toLocaleTimeString()}
                    </Typography>
                  </Paper>
                ))}

                {agentActions.length === 0 && (
                  <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                    No agent activity yet. Send a message to start.
                  </Typography>
                )}

                <div ref={actionsEndRef} />
              </Box>
            </Paper>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle>
            <Box
              sx={{
                width: '3px',
                height: '100%',
                cursor: 'col-resize',
                transition: 'background-color 0.2s'
              }}
            />
          </PanelResizeHandle>

          {/* Right Panel - Browser View */}
          <Panel defaultSize={60} minSize={40}>
            <Paper
              elevation={0}
              className="glass-effect"
              sx={{
                height: '100%',
                borderRadius: 2,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                ml: 0.25
              }}
            >
              {browserState ? (
                <Box sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  height: '100%'
                }}>
                  {/* Browser Header */}
                  <Box sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    p: 1.5,
                    pl: 3,
                    borderBottom: `1px solid ${theme.palette.divider}`,
                    backgroundColor: alpha(theme.palette.background.paper, 0.6),
                    flexShrink: 0 // Prevent header from shrinking
                  }}>
                    <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 500 }}>
                      Browser View
                    </Typography>
                    <Box>
                      <Button
                        variant="text"
                        size="small"
                        startIcon={<OpenInFullIcon />}
                        onClick={() => window.open(`data:image/jpeg;base64,${browserState}`, '_blank')}
                        sx={{
                          textTransform: 'none',
                          color: theme.palette.primary.main
                        }}
                      >
                        Full Size
                      </Button>
                      <Button
                        variant="text"
                        size="small"
                        startIcon={<CloseIcon />}
                        onClick={() => setBrowserState(null)}
                        sx={{
                          textTransform: 'none',
                          color: theme.palette.error.main
                        }}
                      >
                        Close
                      </Button>
                    </Box>
                  </Box>

                  {/* Browser Content */}
                  <Box sx={{
                    flexGrow: 1,
                    overflow: 'auto',
                    position: 'relative',
                    backgroundColor: alpha(theme.palette.background.default, 0.3),
                    p: 3,
                    height: 0, // Ensure container uses flex sizing to enable scrolling
                    minHeight: 0
                  }}>
                    <Paper
                      elevation={0}
                      className="fade-in"
                      sx={{
                        borderRadius: 1.5,
                        overflow: 'hidden',
                        mb: 1,
                        boxShadow: '0 2px 10px rgba(0, 0, 0, 0.15)'
                      }}
                    >
                      <img
                        src={`data:image/jpeg;base64,${browserState}`}
                        alt="Browser Screenshot"
                        className="browser-screenshot"
                        style={{
                          width: '100%',
                          height: 'auto',
                          display: 'block'
                        }}
                        onError={(e) => {
                          // If JPEG fails, try PNG
                          const target = e.target as HTMLImageElement;
                          if (target.src.includes('image/jpeg')) {
                            console.log('Trying PNG format instead');
                            target.src = `data:image/png;base64,${browserState}`;
                          }
                        }}
                      />
                    </Paper>
                    <div ref={browserEndRef} />
                  </Box>
                </Box>
              ) : (
                <Box sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  p: 4,
                  textAlign: 'center'
                }}>
                  <Typography variant="h6" color="text.secondary" sx={{ mb: 2 }}>
                    Browser View
                  </Typography>
                  <Typography variant="body1" color="text.secondary">
                    When the agent uses the browser, the content will appear here.
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    Try asking a question that requires web browsing.
                  </Typography>
                </Box>
              )}
            </Paper>
          </Panel>
        </PanelGroup>
      </Box>
    </Box>
  );
}

export default App;
