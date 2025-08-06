"""
Flow nodes definitions for conversation structure.
"""

from pipecat_flows import FlowsFunctionSchema
from .functions import FlowFunctions


def create_initial_node(functions: FlowFunctions):
    """Create the initial greeting node for the conversation flow."""
    
    collect_name_schema = FlowsFunctionSchema(
        name="collect_name",
        description="Collect the user's name during introduction.",
        handler=functions.collect_name,
        properties={
            "name": {
                "type": "string",
                "description": "The user's name"
            }
        },
        required=["name"]
    )
    
    return {
        "name": "initial",
        "role_messages": [
            {
                "role": "system",
                "content": "You are a friendly AI assistant. Your goal is to have a natural conversation and help the user with their needs."
            }
        ],
        "task_messages": [
            {
                "role": "system",
                "content": "Start by greeting the user warmly and asking for their name to personalize the conversation."
            }
        ],
        "functions": [collect_name_schema]
    }


def create_main_menu_node(functions: FlowFunctions, user_name: str):
    """Create the main menu node after collecting user's name."""
    
    handle_choice_schema = FlowsFunctionSchema(
        name="handle_menu_choice",
        description="Process the user's menu selection.",
        handler=functions.handle_menu_choice,
        properties={
            "choice": {
                "type": "string",
                "enum": ["information", "support", "feedback", "exit"],
                "description": "The user's menu choice"
            }
        },
        required=["choice"]
    )
    
    return {
        "name": "main_menu",
        "role_messages": [
            {
                "role": "system",
                "content": f"You are speaking with {user_name}. Be friendly and helpful."
            }
        ],
        "task_messages": [
            {
                "role": "system",
                "content": f"Thank {user_name} for sharing their name. Present them with options: 1) Get information about our services, 2) Technical support, 3) Provide feedback, or 4) End conversation. Listen to their choice and process it."
            }
        ],
        "functions": [handle_choice_schema]
    }


def create_end_node(user_name: str):
    """Create the ending node for the conversation."""
    
    return {
        "name": "end",
        "role_messages": [
            {
                "role": "system",
                "content": "You are concluding the conversation politely."
            }
        ],
        "task_messages": [
            {
                "role": "system",
                "content": f"Thank {user_name} for the conversation. Say goodbye warmly and let them know they can call back anytime if they need help."
            }
        ],
        "functions": []
    }