"""
Flow function handlers for processing user inputs and managing state.

This module provides handlers for flow nodes, managing user data and state
transitions throughout the conversation flow.
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from pipecat_flows import FlowManager


class FlowFunctions:
    """Handler class for flow functions."""
    
    def __init__(self, flow_manager: 'FlowManager') -> None:
        """Initialize with reference to the flow manager.
        
        Args:
            flow_manager: The FlowManager instance managing this flow
        """
        self.flow_manager: 'FlowManager' = flow_manager
        self.user_data: Dict[str, Any] = {}
    
    async def collect_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Collect user's name and transition to main menu.
        
        Args:
            name: The user's name from the conversation
            
        Returns:
            Transition configuration to next node
        """
        logger.info(f"Collected name: {name}")
        self.user_data['name'] = name
        
        # Import here to avoid circular dependency
        from .nodes import create_main_menu_node
        
        # Transition to main menu
        next_node = create_main_menu_node(self, name)
        return {
            "transition_to": next_node,
            "context_update": {
                "user_name": name
            }
        }
    
    async def handle_menu_choice(self, choice: str) -> Optional[Dict[str, Any]]:
        """
        Handle the user's menu selection.
        
        Args:
            choice: The user's menu choice
            
        Returns:
            Transition configuration based on choice
        """
        logger.info(f"User selected: {choice}")
        
        user_name = self.user_data.get('name', 'User')
        
        if choice == "exit":
            # Import here to avoid circular dependency
            from .nodes import create_end_node
            
            # Transition to end node
            next_node = create_end_node(user_name)
            return {
                "transition_to": next_node
            }
        
        # For now, just log other choices and stay in menu
        # In a real implementation, you'd have nodes for each option
        logger.info(f"Handling {choice} request for {user_name}")
        
        # Stay in current node but acknowledge the choice
        return {
            "context_update": {
                "last_choice": choice,
                "message": f"I understand you want {choice}. Let me help you with that."
            }
        }
    
    def get_user_data(self) -> Dict[str, Any]:
        """Get current user data."""
        return self.user_data
    
    def clear_user_data(self):
        """Clear user data for new session."""
        self.user_data = {}