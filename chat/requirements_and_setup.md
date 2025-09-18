# Local LLM + House Knowledge Graph Chat Setup

## Overview

This chat application integrates a local small LLM with the blowing-off MCP client library to enable conversational interactions with house knowledge graph data from the funkygibbon server test dataset.

**Repository Structure:**
```
the-goodies/
├── blowing-off/           # Your existing MCP client library
├── chat/                  # This chat application (NEW)
│   ├── chat_app.py        # Main application
│   ├── requirements.txt   # Python dependencies  
│   ├── test_setup.py      # Setup verification script
│   ├── models/           # Directory for LLM models (you'll create this)
│   └── .env              # Environment configuration
└── funkygibbon/          # Server with test data (existing)
```

## Requirements

### Hardware Requirements
- **CPU**: Modern multi-core processor (8+ cores recommended)
- **RAM**: 8GB minimum, 16GB+ recommended
- **Storage**: 10GB+ free space for models
- **GPU** (optional): NVIDIA GPU with 4GB+ VRAM for faster inference

### Software Requirements
- Python 3.8+
- Git

## Installation Steps

### 1. Setup Directory Structure

From your `the-goodies` repository root:

```bash
# Create the chat subdirectory
mkdir -p chat/models

# Navigate to chat directory
cd chat

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements (after creating requirements.txt)
pip install -r requirements.txt
```

### 2. Download a Small LLM Model

Choose one of these lightweight models suitable for laptops:

#### Option A: Mistral 7B (Recommended)
```bash
# From the-goodies/chat/ directory
cd models

# Download Mistral 7B Instruct (4-bit quantized, ~4GB)
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf
```

#### Option B: Phi-3 Mini (Smaller, ~2GB)
```bash
# Alternative smaller model
wget https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf
```

#### Option C: TinyLlama (Smallest, ~600MB)
```bash
# For very limited resources
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

### 3. GPU Support (Optional)

If you have an NVIDIA GPU and want faster inference:

```bash
# Uninstall CPU-only version
pip uninstall llama-cpp-python -y

# Install GPU version
CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
```

For Apple Silicon Macs:
```bash
# Uninstall CPU-only version
pip uninstall llama-cpp-python -y

# Install Metal version
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
```

### 4. Verify Blowing-Off MCP Client

Make sure your blowing-off MCP client is working:

```bash
# From the-goodies/ root directory
cd blowing-off

# Test your MCP client/server (replace with actual script name)
python server.py  # or whatever your server script is called

# Verify it connects to funkygibbon and loads test data
```

## Configuration

### Environment Variables

Create a `.env` file in the `chat/` directory:

```env
# LLM Configuration
MODEL_PATH=./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
BLOWING_OFF_SERVER=../blowing-off/server.py

# LLM Parameters (optional, defaults provided)
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=512
LLM_CONTEXT_SIZE=4096
LLM_GPU_LAYERS=0  # Set to > 0 if using GPU

# Logging
LOG_LEVEL=INFO
```

### Model Configuration

You can adjust the LLM parameters in the application code:

```python
self.llm_config = {
    'n_ctx': 4096,          # Context window size
    'n_threads': 8,         # CPU threads to use
    'n_gpu_layers': 0,      # GPU layers (set > 0 for GPU)
    'temperature': 0.7,     # Response creativity (0.0-1.0)
    'max_tokens': 512,      # Maximum response length
    'top_p': 0.9,          # Nucleus sampling
    'repeat_penalty': 1.1   # Avoid repetition
}
```

## Usage

### Basic Usage

```bash
# From the-goodies/chat/ directory
python chat_app.py <model_path> <blowing_off_server_path>

# Examples:
python chat_app.py ./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf ../blowing-off/server.py

# Or with TinyLlama for lighter usage:
python chat_app.py ./models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf ../blowing-off/server.py
```

### Example Conversation

```
🏠 House Knowledge Graph Chat
===================================
Connected to blowing-off MCP client with funkygibbon test data
Ask questions about houses, properties, and neighborhoods!
Type 'quit', 'exit', or 'bye' to end the conversation.

You: What houses are available in the test dataset?
Assistant: Let me check the knowledge graph for house information... TOOL: list_houses()

I found several properties in the test dataset! There's a beautiful Victorian house on Maple Street with 4 bedrooms, a modern downtown condo with 2 bedrooms, and a ranch-style home in the suburbs with 3 bedrooms. Each property has detailed information about square footage, amenities, and pricing.

You: Tell me more about the Victorian house on Maple Street
Assistant: The Victorian house on Maple Street is quite charming! It's a historic property built in 1895 with 4 bedrooms and 3 bathrooms. The house features original hardwood floors, ornate crown molding, and a beautiful wraparound porch. It's been well-maintained with modern updates to the kitchen and electrical systems while preserving its historic character. The property sits on a large lot with mature trees.

You: quit
Goodbye! Thanks for exploring the house data! 👋
```

## Tool Integration

The application uses a simple pattern recognition system to identify when to call MCP tools. The LLM can use tools by including patterns like:

```
TOOL: tool_name(argument1=value1, argument2=value2)
```

You can extend this by:
1. Training the LLM with examples of tool usage
2. Using structured output formats
3. Implementing function calling capabilities

## Troubleshooting

### Common Issues

**1. Model Loading Errors**
```bash
# Check model file exists and is readable
ls -la ./models/your-model.gguf

# Ensure sufficient RAM
free -h  # Linux/Mac
```

**2. Blowing-Off Server Issues**
```bash
# Test blowing-off server independently
cd ../blowing-off
python server.py  # Replace with actual server script name

# Ensure it connects to funkygibbon and loads test data
# Check that the server implements MCP protocol correctly
```

**3. GPU Not Detected**
```bash
# Verify CUDA installation
nvidia-smi

# Check llama-cpp-python GPU support
python -c "from llama_cpp import Llama; print('GPU support available')"
```

**4. Out of Memory Errors**
- Reduce `n_ctx` (context window size)
- Use a smaller model
- Reduce `n_gpu_layers` if using GPU
- Close other applications

### Performance Optimization

**For CPU-only setups:**
- Increase `n_threads` to match your CPU cores
- Use quantized models (Q4_K_M or Q5_K_M)
- Reduce context window size if needed

**For GPU setups:**
- Set `n_gpu_layers` to -1 to use full GPU
- Increase `n_batch` for better throughput
- Monitor GPU memory usage

**For Mobile/Laptop:**
- Use TinyLlama or Phi-3 Mini models
- Reduce context window to 2048 or lower
- Set temperature lower (0.3-0.5) for more focused responses

## Advanced Configuration

### Custom System Prompts

You can modify the system prompt in the `_format_system_prompt()` method to better suit your house data domain:

```python
def _format_system_prompt(self) -> str:
    return f"""You are a knowledgeable real estate AI assistant with access to house data via the blowing-off MCP client. 
    
    Available tools: {tools_description}
    
    Your expertise includes:
    - Property details and specifications from the funkygibbon test dataset
    - House comparisons and market analysis
    - Neighborhood insights and trends
    - Investment potential and recommendations
    
    Always provide helpful, accurate information and cite your sources when using the knowledge graph data."""
```

### Adding More Sophisticated Tool Calling

For more advanced setups, consider implementing:
- JSON-based function calling
- Tool result caching
- Multi-step reasoning with tools
- Error handling and retry logic

## Next Steps

1. Test the basic setup with your blowing-off MCP client
2. Experiment with different models and parameters based on your hardware
3. Enhance the tool calling mechanism for better integration
4. Add conversation memory and context management
5. Consider adding a web interface using Streamlit or FastAPI
6. Explore the funkygibbon test dataset to understand available house data

This setup provides a solid foundation for local LLM + MCP integration that leverages your existing blowing-off client library and funkygibbon test data for house knowledge graph conversations.