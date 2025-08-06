"""
VAPI.AI Workflow to Pipecat Flows Converter

Converts VAPI workflow JSON format to Pipecat Flows node structure.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger


# Constants for VAPI prompt sections
ROLE_MARKER = '[Role]'
CONTEXT_MARKER = '[Context]'
GUIDELINES_MARKER = '[Response Guidelines]'
FLOW_MARKER = '[Conversation Flow]'
SPECIAL_MARKER = '[Special Situations]'


@dataclass
class VAPINode:
    """VAPI workflow node representation."""
    name: str
    type: str
    prompt: Optional[str] = None
    first_message: Optional[str] = None
    is_start: bool = False
    model: Optional[Dict] = None
    tool: Optional[Dict] = None
    variable_extraction: Optional[Dict] = None


@dataclass
class VAPIEdge:
    """VAPI workflow edge representation."""
    from_node: str
    to_node: str
    condition: Dict


class VAPIToPipecatConverter:
    """Converter for VAPI workflows to Pipecat Flow format."""
    
    def __init__(self, vapi_workflow: Dict[str, Any]):
        """
        Initialize converter with VAPI workflow data.
        
        Args:
            vapi_workflow: VAPI workflow dictionary from JSON
        """
        self.workflow: Dict[str, Any] = vapi_workflow
        self.nodes: Dict[str, VAPINode] = {}
        self.edges: List[VAPIEdge] = []
        self.pipecat_nodes: Dict[str, Dict[str, Any]] = {}
        self._parse_workflow()
    
    def _parse_workflow(self):
        """Parse VAPI workflow into internal structures."""
        # Parse nodes
        for node_data in self.workflow.get('nodes', []):
            node = VAPINode(
                name=node_data['name'],
                type=node_data['type'],
                prompt=node_data.get('prompt'),
                is_start=node_data.get('isStart', False),
                model=node_data.get('model'),
                tool=node_data.get('tool'),
                variable_extraction=node_data.get('variableExtractionPlan')
            )
            
            # Extract first message if present
            if 'messagePlan' in node_data and 'firstMessage' in node_data['messagePlan']:
                node.first_message = node_data['messagePlan']['firstMessage']
            
            self.nodes[node.name] = node
        
        # Parse edges
        for edge_data in self.workflow.get('edges', []):
            edge = VAPIEdge(
                from_node=edge_data['from'],
                to_node=edge_data['to'],
                condition=edge_data.get('condition', {})
            )
            self.edges.append(edge)
    
    
    def _convert_node_to_pipecat(self, node: VAPINode) -> Dict[str, Any]:
        """
        Convert a VAPI node to Pipecat Flow node format.
        
        Args:
            node: VAPI node to convert
            
        Returns:
            Pipecat Flow node dictionary
        """
        pipecat_node = {
            "name": node.name,
            "role_messages": [],
            "task_messages": [],
            "functions": []  # Will store function definitions, not instances
        }
        
        # Convert prompt to role/task messages
        if node.prompt:
            # Parse VAPI prompt structure
            prompt_text = node.prompt
            
            # Extract sections using regex-like approach
            role_content = []
            context_content = []
            guidelines_content = []
            flow_content = []
            
            current_section: Optional[str] = None
            for line in prompt_text.split('\n'):
                if ROLE_MARKER in line:
                    current_section = 'role'
                    continue
                elif CONTEXT_MARKER in line:
                    current_section = 'context'
                    continue
                elif GUIDELINES_MARKER in line:
                    current_section = 'guidelines'
                    continue
                elif FLOW_MARKER in line:
                    current_section = 'flow'
                    continue
                elif SPECIAL_MARKER in line:
                    current_section = 'special'
                    continue
                
                # Add line to appropriate section
                if current_section == 'role' and line.strip():
                    role_content.append(line.strip())
                elif current_section == 'context' and line.strip():
                    context_content.append(line.strip())
                elif current_section == 'guidelines' and line.strip():
                    guidelines_content.append(line.strip())
                elif current_section in ['flow', 'special'] and line.strip():
                    flow_content.append(line.strip())
            
            # Build role message
            if role_content or context_content:
                role_msg = []
                if role_content:
                    role_msg.extend(role_content)
                if context_content:
                    role_msg.append("\nContext:")
                    role_msg.extend(context_content)
                
                pipecat_node["role_messages"].append({
                    "role": "system",
                    "content": '\n'.join(role_msg)
                })
            
            # Build task message
            if guidelines_content or flow_content:
                task_msg = []
                if guidelines_content:
                    task_msg.append("Guidelines:")
                    task_msg.extend(guidelines_content)
                if flow_content:
                    if guidelines_content:
                        task_msg.append("")  # Add blank line
                    task_msg.append("Conversation Flow:")
                    task_msg.extend(flow_content)
                
                pipecat_node["task_messages"].append({
                    "role": "system",
                    "content": '\n'.join(task_msg)
                })
        
        # Add first message if it's a start node
        if node.first_message:
            pipecat_node["task_messages"].append({
                "role": "system",
                "content": f"Start the conversation with: {node.first_message}"
            })
        
        # Handle tool nodes (end call nodes)
        if node.type == 'tool' and node.tool:
            if node.tool.get('type') == 'endCall':
                # Get the farewell message
                messages = node.tool.get('messages', [])
                if messages:
                    farewell = messages[0].get('content', 'Goodbye!')
                    pipecat_node["task_messages"].append({
                        "role": "system",
                        "content": f"End the conversation by saying: {farewell}"
                    })
        
        # Add transition functions based on edges
        outgoing_edges = [e for e in self.edges if e.from_node == node.name]
        if outgoing_edges:
            # Store function definition as dict instead of FlowsFunctionSchema
            pipecat_node["functions"].append({
                "name": f"transition_from_{node.name}",
                "description": f"Determine next step based on conversation state for {node.name}",
                "targets": [edge.to_node for edge in outgoing_edges],
                "conditions": [
                    {
                        "target": edge.to_node,
                        "condition": edge.condition.get('prompt', '') if edge.condition.get('type') == 'ai' else ''
                    }
                    for edge in outgoing_edges
                ]
            })
        
        # Handle variable extraction
        if node.variable_extraction:
            outputs = node.variable_extraction.get('output', [])
            for output in outputs:
                var_name = output.get('title', 'variable')
                var_desc = output.get('description', '')
                
                # Store extraction function definition as dict
                pipecat_node["functions"].append({
                    "name": f"extract_{var_name}",
                    "description": f"Extract {var_desc}",
                    "type": "extraction",
                    "variable": var_name,
                    "variable_type": output.get('type', 'string'),
                    "variable_description": var_desc
                })
        
        return pipecat_node
    
    def convert(self) -> Dict[str, Any]:
        """
        Convert the entire VAPI workflow to Pipecat Flow format.
        
        Returns:
            Dictionary containing converted flow configuration
        """
        logger.info(f"Converting VAPI workflow: {self.workflow.get('name', 'Unnamed')}")
        
        # Convert all nodes
        for node_name, node in self.nodes.items():
            pipecat_node = self._convert_node_to_pipecat(node)
            self.pipecat_nodes[node_name] = pipecat_node
        
        # Find start node
        start_node = None
        for node in self.nodes.values():
            if node.is_start:
                start_node = node.name
                break
        
        # Build flow configuration
        flow_config = {
            "name": self.workflow.get('name', 'Converted Flow'),
            "start_node": start_node,
            "nodes": self.pipecat_nodes,
            "edges": [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "condition": edge.condition
                }
                for edge in self.edges
            ]
        }
        
        # Add metadata for reference (not used by Pipecat)
        flow_config["metadata"] = {
            "source": "VAPI workflow conversion",
            "original_model": self.workflow.get('model', {}),
            "original_voice": self.workflow.get('voice', {})
        }
        
        logger.info(f"Conversion complete: {len(self.pipecat_nodes)} nodes, {len(self.edges)} edges")
        
        return flow_config


def load_and_convert_vapi_workflow(file_path: str) -> Dict[str, Any]:
    """
    Load and convert a VAPI workflow file to Pipecat Flow format.
    
    Args:
        file_path: Path to VAPI workflow JSON file
        
    Returns:
        Converted Pipecat Flow configuration
        
    Raises:
        FileNotFoundError: If the workflow file doesn't exist
        json.JSONDecodeError: If the workflow file is not valid JSON
        ValueError: If the workflow format is invalid
    """
    # Validate file path
    workflow_path = Path(file_path)
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {file_path}")
    
    if not workflow_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")
    
    logger.info(f"Loading VAPI workflow from: {file_path}")
    
    try:
        with open(workflow_path, 'r') as f:
            vapi_workflow = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in workflow file: {e}")
        raise
    except Exception as e:
        logger.error(f"Error reading workflow file: {e}")
        raise
    
    if not isinstance(vapi_workflow, dict):
        raise ValueError("Workflow must be a JSON object")
    
    converter = VAPIToPipecatConverter(vapi_workflow)
    return converter.convert()


if __name__ == "__main__":
    # Test conversion with the provided workflow
    import sys
    
    if len(sys.argv) > 1:
        workflow_file = sys.argv[1]
    else:
        # Use Path for safer path operations
        workflow_file = str(Path(__file__).parent.parent / "docs" / "lead-nurturing-agent---demo-simplified-0803.json")
    
    try:
        pipecat_flow = load_and_convert_vapi_workflow(workflow_file)
        
        # Save converted flow
        output_path = Path(workflow_file)
        output_file = output_path.with_name(output_path.stem + '_pipecat.json')
        
        try:
            with open(output_file, 'w') as f:
                json.dump(pipecat_flow, f, indent=2)
            logger.success(f"Converted workflow saved to: {output_file}")
        except IOError as e:
            logger.error(f"Failed to save converted workflow: {e}")
            sys.exit(1)
        
        # Print summary
        print("\n=== Conversion Summary ===")
        print(f"Flow Name: {pipecat_flow['name']}")
        print(f"Start Node: {pipecat_flow['start_node']}")
        print(f"Total Nodes: {len(pipecat_flow['nodes'])}")
        print(f"Total Edges: {len(pipecat_flow['edges'])}")
        print("\nNodes:")
        for node_name in pipecat_flow['nodes']:
            print(f"  - {node_name}")
        
    except FileNotFoundError as e:
        logger.error(f"Workflow file not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in workflow file: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid workflow format: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during conversion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)