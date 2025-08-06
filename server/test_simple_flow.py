"""
Simple test to verify basic Pipecat Flows integration.
"""

import asyncio
import os
from dotenv import load_dotenv
from loguru import logger

# Test imports
try:
    from pipecat_flows import FlowManager, FlowsFunctionSchema
    logger.info("✅ pipecat_flows imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import pipecat_flows: {e}")
    logger.info("Please run: pip install pipecat-ai-flows")
    exit(1)

load_dotenv(override=True)


async def test_basic_flow():
    """Test basic flow functionality."""
    
    logger.info("\n=== Testing Basic Flow Setup ===")
    
    # Test function handler
    async def test_handler(args: dict) -> dict:
        logger.info(f"Handler called with: {args}")
        return {"status": "success", "data": args}
    
    # Create a function schema
    test_function = FlowsFunctionSchema(
        name="test_function",
        description="A test function",
        handler=test_handler,
        properties={
            "test_param": {"type": "string", "description": "A test parameter"}
        },
        required=["test_param"]
    )
    
    logger.info(f"✅ Created function schema: {test_function.name}")
    
    # Test function execution
    result = await test_function.handler({"test_param": "hello"})
    assert result["status"] == "success", "Handler should return success"
    logger.info(f"✅ Function executed successfully: {result}")
    
    # Create a flow manager
    flow_manager = FlowManager(
        initial_messages=[
            {"role": "system", "content": "You are a test bot"}
        ]
    )
    
    logger.info("✅ FlowManager created successfully")
    
    return True


async def test_environment():
    """Test that required environment variables are set."""
    
    logger.info("\n=== Testing Environment Variables ===")
    
    required_vars = ["DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        if os.getenv(var):
            logger.info(f"✅ {var} is set")
        else:
            logger.warning(f"⚠️  {var} is not set")
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"\nMissing environment variables: {', '.join(missing_vars)}")
        logger.info("Please set these in your .env file to run the bot")
    
    return len(missing_vars) == 0


async def main():
    """Run all tests."""
    
    logger.info("Starting Simple Pipecat Flows Integration Test")
    logger.info("=" * 50)
    
    # Test environment
    env_ok = await test_environment()
    
    # Test basic flow
    try:
        flow_ok = await test_basic_flow()
    except Exception as e:
        logger.error(f"Flow test failed: {e}")
        import traceback
        traceback.print_exc()
        flow_ok = False
    
    logger.info("\n" + "=" * 50)
    
    if flow_ok:
        logger.success("✅ Basic Pipecat Flows integration is working!")
        logger.info("\nNext steps:")
        logger.info("1. Run the simple flow bot: python bot_simple_flow.py")
        logger.info("2. Connect from the client at http://localhost:5173")
        logger.info("3. Test the conversation flow")
    else:
        logger.error("❌ Some tests failed. Please check the errors above.")
    
    if not env_ok:
        logger.info("\n💡 Tip: Copy env.example to .env and add your API keys")


if __name__ == "__main__":
    asyncio.run(main())