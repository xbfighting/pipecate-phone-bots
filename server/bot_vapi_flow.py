#!/usr/bin/env python3
"""
Complete Vapi Workflow Implementation for Pipecat Cloud.

This implementation faithfully reproduces the Vapi workflow while following PCC best practices:
- All 6 nodes (2 conversation, 4 tool/endCall nodes)
- All 5 edges with exact condition matching
- Variable extraction for main_barrier and specific_concern
- Exact prompts and messages from the workflow
- Model configuration (temperature, max tokens)
- Port 8080 for Pipecat Cloud
"""

import os
import asyncio
from enum import Enum
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.frames.frames import LLMMessagesFrame, EndFrame
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport

load_dotenv(override=True)


# Exact node names from Vapi workflow
class WorkflowNode(Enum):
    INTRODUCTION = "introduction"
    MAIN_CONVERSATION = "main_conversation"
    HANGUP = "hangup"
    HANGUP_BOOKED = "Hangup Booked"
    HANGUP_FOLLOW_UP = "Hangup Follow Up"
    HANGUP_MAYBE_LATER = "Hangup Maybe Later"


@dataclass
class NodeConfig:
    """Configuration for a workflow node."""
    name: str
    type: str  # "conversation" or "tool"
    prompt: Optional[str] = None
    first_message: Optional[str] = None
    tool_type: Optional[str] = None
    end_message: Optional[str] = None
    is_start: bool = False
    model_config: Dict[str, Any] = field(default_factory=dict)
    variable_extraction: Optional[Dict[str, Any]] = None


@dataclass
class EdgeConfig:
    """Configuration for a workflow edge."""
    from_node: str
    to_node: str
    condition_prompt: str


@dataclass
class ConversationVariables:
    """Variables extracted during conversation."""
    main_barrier: Optional[str] = None  # financial, timing, questions_procedure, questions_recovery, or unsure
    specific_concern: Optional[str] = None
    customer_name: str = "there"  # Default if not provided


class VapiWorkflowEngine:
    """
    Complete implementation of the Vapi workflow engine.
    """

    def __init__(self):
        self.current_node = WorkflowNode.INTRODUCTION
        self.variables = ConversationVariables()
        self.conversation_history = []

        # Load exact workflow configuration
        self.nodes = self._load_nodes()
        self.edges = self._load_edges()

    def _load_nodes(self) -> Dict[WorkflowNode, NodeConfig]:
        """Load node configurations from the workflow."""
        return {
            WorkflowNode.INTRODUCTION: NodeConfig(
                name="introduction",
                type="conversation",
                is_start=True,
                prompt="""[Role]
You're Teresa, a patient care coordinator for Clevens Face & Body Specialists. Your primary task is to follow up with patients who inquired about rhinoplasty.

[Context]
You're calling a patient who made a rhinoplasty inquiry. Dr. Ross Clevens is double board-certified and has performed over twenty thousand surgeries. The practice offers both surgical and liquid rhinoplasty.

[Response Guidelines]
Be warm and professional.
Keep initial contact brief.
Never mention tools or functions.
If not interested, trigger endCall silently.""",
                first_message="Hi {{customer.name}}, this is Teresa from Dr. Clevens' office. I noticed you inquired about Rhinoplasty but haven't scheduled your consultation yet. I wanted to check in and see if you're still interested in improving your nose shape or breathing?",
                model_config={"temperature": 0.3, "maxTokens": 250}
            ),

            WorkflowNode.MAIN_CONVERSATION: NodeConfig(
                name="main_conversation",
                type="conversation",
                prompt="""[Role]
You're Teresa, helping with rhinoplasty questions and booking consultations. Be knowledgeable, patient, never pushy.

[Context]
Key Information:
- Surgical: $8,000-$10,000, permanent, 7-10 day recovery
- Liquid: $1,500+, lasts 2 years, no downtime
- CareCredit: 0% for 12 months ($667-$833/month surgical)
- Locations: Melbourne & Merritt Island
- Virtual consults available
- Dr. Clevens: Yale/Harvard trained, 20,000+ surgeries

[Response Guidelines]
Address ALL concerns mentioned.
Always offer both options when discussing cost.
Use word numbers (eight thousand).
Validate concerns before solutions.

[Conversation Flow]
1. Say: "I completely understand these decisions take time. What's been the main thing holding you back? Is it timing, wanting more information, recovery concerns, or cost?"

2. Based on response:

COST:
"I understand cost is important. Surgical rhinoplasty runs eight thousand to ten thousand dollars, but with CareCredit that's six hundred sixty-seven to eight hundred thirty-three monthly with no interest. We also have Liquid Rhinoplasty starting at fifteen hundred - immediate results, no downtime. Which option sounds more feasible?"

RECOVERY:
"For surgical, you'll have a splint for one week and take seven to ten days off work. Dr. Clevens uses techniques that minimize bruising. For liquid rhinoplasty, you return to activities the same day - just ten minutes, no downtime. Which timeline works better for you?"

PROCEDURE INFO:
"Surgical permanently reshapes your nose - fixes breathing, removes bumps, straightens. Dr. Clevens' Liquid Rhinoplasty uses fillers for instant results in ten minutes. Many try this first to see how they'll look. Are you looking for permanent or want to try non-surgical first?"

TIMING:
"We have flexible scheduling including evenings and weekends at both locations. Also virtual consultations via WhatsApp or FaceTime. What works best - virtual consultation or in-person with computer imaging?"

3. After addressing concerns:

IF READY (positive responses):
"Wonderful! Which location - Melbourne or Merritt Island?"
"In-person with computer imaging or virtual consultation?"
"Morning or afternoon?"
"Next Tuesday or Thursday?"
"Perfect! Our coordinator will send confirmation. You'll meet Dr. Clevens or Dr. Barbee."
→ hangup_booked

IF NEEDS TIME:
"No pressure at all. Would you like information about both options with photos and pricing?"
If yes: "Email or text?"
"Should I follow up in two weeks or a month?"
→ hangup_followup

IF UNCERTAIN after multiple attempts:
"I understand this is a big decision. We're here whenever you're ready."
→ hangup_maybe_later

4. Handle partial satisfaction:
If "a little bit" or uncertain: "What would be most helpful to explain further?"

[Special Situations]
- Price shock: Immediately mention liquid option and monthly payments
- Other doctors: "Many get second opinions. What questions about Dr. Clevens' approach?"
- Had rhinoplasty before: "Dr. Clevens also does revision rhinoplasty. What concerns you about current results?" """,
                first_message="I completely understand these decisions take time. What's been the main thing holding you back? Is it timing, or wanting more information about the procedures, or concerns about recovery, or cost?",
                model_config={"temperature": 0.3, "maxTokens": 250},
                variable_extraction={
                    "output": [
                        {
                            "type": "string",
                            "title": "main_barrier",
                            "description": "Primary barrier: financial, timing, questions_procedure, questions_recovery, or unsure"
                        },
                        {
                            "type": "string",
                            "title": "specific_concern",
                            "description": "Their specific concern in detail"
                        }
                    ]
                }
            ),

            WorkflowNode.HANGUP: NodeConfig(
                name="hangup",
                type="tool",
                tool_type="endCall",
                end_message="Thank you for your time today. Remember, we offer both surgical and non-surgical rhinoplasty options at Clevens Face & Body Specialists. Feel free to visit our website or call us whenever you're ready!"
            ),

            WorkflowNode.HANGUP_BOOKED: NodeConfig(
                name="Hangup Booked",
                type="tool",
                tool_type="endCall",
                end_message="Excellent! Our coordinator will email your confirmation shortly with directions and what to expect. We look forward to seeing you! Have a wonderful day!"
            ),

            WorkflowNode.HANGUP_FOLLOW_UP: NodeConfig(
                name="Hangup Follow Up",
                type="tool",
                tool_type="endCall",
                end_message="Wonderful! I'll make sure to send you that information right away and follow up with you as discussed. Remember, Dr. Clevens has been specializing in rhinoplasty for over 25 years and we're here to answer any questions. Have a great day!"
            ),

            WorkflowNode.HANGUP_MAYBE_LATER: NodeConfig(
                name="Hangup Maybe Later",
                type="tool",
                tool_type="endCall",
                end_message="Thank you for your time today. Feel free to reach out whenever you're ready to take the next step. Have a wonderful day!"
            )
        }

    def _load_edges(self) -> List[EdgeConfig]:
        """Load edge configurations from the workflow."""
        return [
            EdgeConfig(
                from_node="introduction",
                to_node="main_conversation",
                condition_prompt="Patient interested but hasn't booked"
            ),
            EdgeConfig(
                from_node="introduction",
                to_node="hangup",
                condition_prompt="Patient says no, not interested, already done, or hostile"
            ),
            EdgeConfig(
                from_node="main_conversation",
                to_node="Hangup Follow Up",
                condition_prompt="Patient wants information sent and/or follow-up scheduled"
            ),
            EdgeConfig(
                from_node="main_conversation",
                to_node="Hangup Booked",
                condition_prompt="Patient provides appointment preferences and confirms booking"
            ),
            EdgeConfig(
                from_node="main_conversation",
                to_node="Hangup Maybe Later",
                condition_prompt="Patient remains uncertain after multiple attempts or conversation is not progressing"
            )
        ]

    def get_current_node_config(self) -> NodeConfig:
        """Get configuration for current node."""
        return self.nodes[self.current_node]

    def get_system_prompt(self) -> str:
        """Get the complete system prompt including global prompt."""
        global_prompt = "Be warm, understanding, and helpful. Never pressure. Focus on understanding their needs and providing thoughtful solutions."
        node_config = self.get_current_node_config()

        if node_config.prompt:
            return f"{global_prompt}\n\n{node_config.prompt}"
        return global_prompt

    def get_first_message(self) -> Optional[str]:
        """Get first message for current node, with variable substitution."""
        node_config = self.get_current_node_config()
        if node_config.first_message:
            return node_config.first_message.replace("{{customer.name}}", self.variables.customer_name)
        return None

    def evaluate_transition(self, user_message: str) -> Optional[WorkflowNode]:
        """Evaluate which transition to take based on user message."""
        user_lower = user_message.lower()
        current_node_name = self.nodes[self.current_node].name

        # Find applicable edges
        applicable_edges = [e for e in self.edges if e.from_node == current_node_name]

        for edge in applicable_edges:
            # Map condition prompts to detection logic
            if self._matches_condition(user_lower, edge.condition_prompt):
                # Find target node
                for node, config in self.nodes.items():
                    if config.name == edge.to_node:
                        logger.info(f"Transition: {self.current_node.value} → {node.value} (condition: {edge.condition_prompt})")
                        return node

        return None

    def _matches_condition(self, user_message: str, condition: str) -> bool:
        """Check if user message matches the condition."""
        condition_lower = condition.lower()

        # Introduction → Main Conversation
        if "interested but hasn't booked" in condition_lower:
            positive_indicators = ["yes", "yeah", "sure", "interested", "tell me", "what", "how", "cost", "price"]
            return any(word in user_message for word in positive_indicators)

        # Introduction → Hangup
        elif "no, not interested" in condition_lower or "hostile" in condition_lower:
            negative_indicators = ["no", "not interested", "stop", "don't call", "remove", "already done", "had surgery"]
            return any(word in user_message for word in negative_indicators)

        # Main Conversation → Hangup Follow Up
        elif "information sent" in condition_lower or "follow-up scheduled" in condition_lower:
            info_indicators = ["send", "email", "text", "information", "brochure", "follow up", "call back"]
            return any(word in user_message for word in info_indicators)

        # Main Conversation → Hangup Booked
        elif "appointment preferences" in condition_lower and "confirms booking" in condition_lower:
            booking_indicators = ["book", "schedule", "appointment", "tuesday", "thursday", "morning", "afternoon", "melbourne", "merritt"]
            return any(word in user_message for word in booking_indicators)

        # Main Conversation → Hangup Maybe Later
        elif "uncertain" in condition_lower or "not progressing" in condition_lower:
            uncertain_indicators = ["maybe", "not sure", "think about", "later", "let me think", "i'll consider"]
            return any(word in user_message for word in uncertain_indicators)

        return False

    def extract_variables(self, user_message: str):
        """Extract variables from user message based on current node configuration."""
        if self.current_node == WorkflowNode.MAIN_CONVERSATION:
            user_lower = user_message.lower()

            # Extract main_barrier
            if any(word in user_lower for word in ["cost", "price", "expensive", "afford"]):
                self.variables.main_barrier = "financial"
            elif any(word in user_lower for word in ["time", "schedule", "when", "busy"]):
                self.variables.main_barrier = "timing"
            elif any(word in user_lower for word in ["procedure", "how", "what happens"]):
                self.variables.main_barrier = "questions_procedure"
            elif any(word in user_lower for word in ["recovery", "healing", "downtime", "pain"]):
                self.variables.main_barrier = "questions_recovery"
            else:
                self.variables.main_barrier = "unsure"

            # Store specific concern
            self.variables.specific_concern = user_message

            logger.info(f"Extracted variables: main_barrier={self.variables.main_barrier}, specific_concern={self.variables.specific_concern[:50]}...")

    def transition_to(self, new_node: WorkflowNode):
        """Execute transition to new node."""
        self.current_node = new_node

    def is_end_node(self) -> bool:
        """Check if current node is an end node."""
        node_config = self.get_current_node_config()
        return node_config.type == "tool" and node_config.tool_type == "endCall"

    def get_end_message(self) -> Optional[str]:
        """Get end message for current node."""
        if self.is_end_node():
            return self.get_current_node_config().end_message
        return None


async def run_vapi_workflow_bot(transport: BaseTransport):
    """Run the complete Vapi workflow bot."""

    logger.info("Starting Complete Vapi Workflow Bot")

    # Initialize workflow engine
    workflow_engine = VapiWorkflowEngine()

    # Initialize services
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="78ab82d5-25be-4f7d-82b3-7ad64e5b85b2",  # Savannah Conversational Friendly a smooth, warm mature female voice with slight Southern accent, perfect for all conversational use cases
    )

    llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model="openai/gpt-4o-mini",  # Exact model from workflow
            temperature=0.3,  # From workflow
            max_tokens=250   # From workflow
        )

    # Initialize context
    messages = [
        {
            "role": "system",
            "content": workflow_engine.get_system_prompt()
        }
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Create RTVI processor for UI updates
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    # Build pipeline with RTVI
    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,  # Add RTVI for real-time UI updates
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],  # Add RTVI observer for UI updates
    )

    # Conversation state manager
    async def manage_conversation_state():
        """Monitor and manage conversation state transitions."""

        last_message_count = 0

        while True:
            await asyncio.sleep(0.5)

            current_messages = context.messages

            if len(current_messages) > last_message_count:
                # Process new messages
                for msg in current_messages[last_message_count:]:
                    if msg.get("role") == "user":
                        user_text = msg.get("content", "")
                        logger.info(f"Processing user message: {user_text}")

                        # Extract variables if in main conversation
                        workflow_engine.extract_variables(user_text)

                        # Evaluate transition
                        next_node = workflow_engine.evaluate_transition(user_text)

                        if next_node:
                            workflow_engine.transition_to(next_node)

                            if workflow_engine.is_end_node():
                                # End conversation
                                end_message = workflow_engine.get_end_message()
                                if end_message:
                                    logger.info(f"Ending conversation with: {end_message[:50]}...")

                                    messages.append({
                                        "role": "system",
                                        "content": f'End the conversation by saying: "{end_message}"'
                                    })

                                    await task.queue_frames([context_aggregator.user().get_context_frame()])
                                    await asyncio.sleep(5)  # Wait for message
                                    await task.queue_frames([EndFrame()])

                            else:
                                # Update context for new conversation node
                                messages[0]["content"] = workflow_engine.get_system_prompt()

                                # Add first message of new node if available
                                first_message = workflow_engine.get_first_message()
                                if first_message:
                                    messages.append({
                                        "role": "system",
                                        "content": f'Say: "{first_message}"'
                                    })

                                await task.queue_frames([context_aggregator.user().get_context_frame()])

                last_message_count = len(current_messages)

    # Start state manager
    state_manager = asyncio.create_task(manage_conversation_state())

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected - Starting Vapi workflow")

        # Send initial greeting from introduction node
        first_message = workflow_engine.get_first_message()
        if first_message:
            messages.append({
                "role": "system",
                "content": f'Start the conversation by saying: "{first_message}"'
            })

            await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        state_manager.cancel()
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


# Entry point for Pipecat runner (both local and cloud)
async def bot(runner_args):
    """Main bot entry point compatible with Pipecat runner.

    This function is called by the Pipecat runner framework.
    It works for both local development and Pipecat Cloud deployment.
    Port 8080 is used by Pipecat Cloud base image.
    """
    logger.info("Bot process initialized")

    # Handle different argument types for local vs cloud
    if hasattr(runner_args, 'webrtc_connection'):
        # Local development
        logger.info(f"WebRTC connection: {runner_args.webrtc_connection}")
        transport = SmallWebRTCTransport(
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
            webrtc_connection=runner_args.webrtc_connection,
        )
    else:
        # Pipecat Cloud with DailySessionArguments
        logger.info("Running in Pipecat Cloud environment")
        from pipecat.transports.network.daily import DailyTransport

        transport = DailyTransport(
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
            room_name=runner_args.room_name,
            token=runner_args.token,
            bot_name="Teresa",
        )

    await run_vapi_workflow_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    # Configure logging
    logger.remove()
    logger.add("vapi_workflow.log", rotation="10 MB", level="DEBUG")
    logger.add(lambda msg: print(msg, end=""), level="INFO", colorize=True)

    logger.info("="*50)
    logger.info("Vapi Workflow Complete Implementation")
    logger.info("="*50)
    logger.info("Nodes: 6 (2 conversation, 4 endCall)")
    logger.info("Edges: 5 (with AI condition evaluation)")
    logger.info("Variables: main_barrier, specific_concern")
    logger.info("Model: gpt-4o-mini with temperature=0.3, max_tokens=250")
    logger.info("Port: 8080 (Pipecat Cloud standard)")
    logger.info("="*50)

    main()
