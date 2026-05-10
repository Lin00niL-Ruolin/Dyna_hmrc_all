# bestman/dynahmrc/core/planner.py
"""
Planning Module - LLM-based task planning and action generation
"""

from typing import Dict, Any, List
import time

class PlanningModule:
    """
    Manages LLM interaction for task planning
    Supports different planning stages
    """
    
    def __init__(self, llm_client, prompt_templates: Dict[str, str]):
        self.llm_client = llm_client
        self.prompts = prompt_templates
        self.call_count = 0
        self.total_latency = 0
        
    def generate(self, prompt: str, temperature: float = 0.5, max_tokens: int = 1024) -> str:
        """
        Generate response from LLM
        Tracks API usage and latency
        """
        start_time = time.time()
        
        try:
            response = self.llm_client.complete(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            latency = time.time() - start_time
            self.total_latency += latency
            self.call_count += 1
            
            return response
            
        except Exception as e:
            print(f"LLM API error: {e}")
            # Fallback response
            return '{"type": "wait", "reason": "llm_error"}'
    
    def get_stats(self) -> Dict:
        """Get LLM usage statistics"""
        avg_latency = self.total_latency / self.call_count if self.call_count > 0 else 0
        return {
            'call_count': self.call_count,
            'total_latency': self.total_latency,
            'avg_latency': avg_latency
        }


class LLMClient:
    """
    Wrapper for LLM API (OpenAI, Claude, Local models)
    """
    
    def __init__(self, api_type: str = "openai", api_key: str = None, model: str = "gpt-4o"):
        self.api_type = api_type
        self.api_key = api_key
        self.model = model
        
        if api_type == "openai":
            import openai
            self.client = openai.OpenAI(api_key=api_key)
        elif api_type == "mock":
            self.client = None  # For testing
    
    def complete(self, prompt: str, temperature: float = 0.5, max_tokens: int = 1024) -> str:
        """Complete prompt with LLM"""
        if self.api_type == "mock":
            return self._mock_response(prompt)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a robot task planning assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"LLM API call failed: {e}")
            return self._fallback_response(prompt)
    
    def _mock_response(self, prompt: str) -> str:
        """Generate mock response for testing"""
        # Simple rule-based mock for testing without API
        if "navigate" in prompt.lower():
            return '{"type": "navigate", "target": "table_0", "stand_pose": 0}'
        elif "pick" in prompt.lower():
            return '{"type": "pick", "target_object": "apple"}'
        elif "place" in prompt.lower():
            return '{"type": "place", "target_object": "apple", "target_location": "tray"}'
        else:
            return '{"type": "wait"}'
    
    def _fallback_response(self, prompt: str) -> str:
        """Safe fallback when API fails"""
        return '{"type": "wait", "reason": "api_error"}'