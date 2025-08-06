#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Client-Server Web Example with Simple Pipecat Flows Integration.

This is a simplified version that integrates basic flow management
with the existing bot architecture.

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run the bot using::

    python bot_simple_flow.py
"""

import os
import sys
from typing import Dict, Any

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport

# Pipecat Flows imports
from pipecat_flows import FlowManager, FlowsFunctionSchema

load_dotenv(override=True)

# Configuration
VOICE_CONFIG = {
    "cartesia_voice_id": "71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
}

MODEL_CONFIG = {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "openai/gpt-4o-mini",
    "temperature": 0.3,
    "max_tokens": 250
}


class SimpleFlowBot:
    """Simple flow-based bot implementation."""
    
    def __init__(self):
        self.user_data: Dict[str, Any] = {}
        self.current_state: str = "greeting"
    
    async def collect_name(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Collect user's name."""
        name = args.get("name", "")
        logger.info(f"Collected name: {name}")
        self.user_data["name"] = name
        self.current_state = "menu"
        return {"status": "success", "next_state": "menu"}
    
    async def handle_menu(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle menu selection."""
        choice = args.get("choice", "")
        logger.info(f"Menu choice: {choice}")
        if choice == "exit":
            self.current_state = "goodbye"
            return {"status": "success", "next_state": "goodbye"}
        return {"status": "success", "message": f"Handling {choice}"}


async def run_bot(transport: BaseTransport):
    logger.info(f"Starting bot with simple flows")
    
    # Validate API keys
    required_keys = ["DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY"]
    missing_keys = [key for key in required_keys if not os.getenv(key)]
    
    if missing_keys:
        logger.error(f"Missing required API keys: {', '.join(missing_keys)}")
        logger.info("Please set these in your .env file")
        sys.exit(1)

    try:
        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    except Exception as e:
        logger.error(f"Failed to initialize Deepgram STT: {e}")
        raise

    try:
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id=VOICE_CONFIG["cartesia_voice_id"],
        )
    except Exception as e:
        logger.error(f"Failed to initialize Cartesia TTS: {e}")
        raise

    try:
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=MODEL_CONFIG["base_url"],
            model=MODEL_CONFIG["model"],
            temperature=MODEL_CONFIG["temperature"],
            max_tokens=MODEL_CONFIG["max_tokens"]
        )
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI LLM: {e}")
        raise

    # Create flow bot instance
    flow_bot = SimpleFlowBot()
    
    # Define functions for flow
    collect_name_fn = FlowsFunctionSchema(
        name="collect_name",
        description="Collect the user's name",
        handler=flow_bot.collect_name,
        properties={
            "name": {"type": "string", "description": "User's name"}
        },
        required=["name"]
    )
    
    handle_menu_fn = FlowsFunctionSchema(
        name="handle_menu",
        description="Handle menu selection",
        handler=flow_bot.handle_menu,
        properties={
            "choice": {
                "type": "string",
                "enum": ["information", "support", "feedback", "exit"],
                "description": "Menu choice"
            }
        },
        required=["choice"]
    )

    # Initial messages with flow context
    messages = [
        {
            "role": "system",
            "content": """You are a friendly AI assistant with a structured conversation flow.
            
Current flow:
1. First, greet the user warmly and ask for their name (use collect_name function)
2. After getting their name, present a menu with options:
   - Get information about services
   - Technical support
   - Provide feedback
   - Exit conversation
3. Process their choice using handle_menu function
4. If they choose exit, say goodbye warmly

Always be conversational and natural in your responses."""
        },
    ]
    
    # Add functions to messages for OpenAI
    llm.function_schemas = [collect_name_fn, handle_menu_fn]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,  # RTVI processor
            stt,
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected - starting flow")
        
        # Reset flow state
        flow_bot.user_data = {}
        flow_bot.current_state = "greeting"
        
        # Start the conversation
        messages.append({
            "role": "system", 
            "content": "Start the conversation by greeting the user warmly and asking for their name."
        })
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the bot starter."""

    transport = SmallWebRTCTransport(
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
        webrtc_connection=runner_args.webrtc_connection,
    )

    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()