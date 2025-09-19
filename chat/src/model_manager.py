"""
Model Manager for Multi-LLM Support
====================================

Manages loading and configuration of multiple LLM models for comparison.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Any
from llama_cpp import Llama

logger = logging.getLogger(__name__)


class ModelManager:
    """Manage multiple LLM models for comparison"""

    # Model configurations
    MODELS = {
        'mistral': {
            'path': 'models/mistral-7b-instruct-v0.2.Q4_K_M.gguf',
            'config': {
                'n_ctx': 4096,
                'n_threads': 8,
                'n_gpu_layers': 0,  # Set > 0 for GPU acceleration
                'verbose': False
            },
            'description': 'Mistral 7B - Best accuracy, higher resource usage'
        },
        'phi3': {
            'path': 'models/Phi-3-mini-4k-instruct-q4.gguf',
            'config': {
                'n_ctx': 4096,
                'n_threads': 8,
                'n_gpu_layers': 0,
                'verbose': False
            },
            'description': 'Phi-3 Mini - Good balance of speed and accuracy'
        },
        'tinyllama': {
            'path': 'models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf',
            'config': {
                'n_ctx': 2048,
                'n_threads': 4,
                'n_gpu_layers': 0,
                'verbose': False
            },
            'description': 'TinyLlama 1.1B - Fast and lightweight'
        }
    }

    def __init__(self, base_path: Path = None):
        """
        Initialize model manager

        Args:
            base_path: Base path for model files (defaults to chat directory)
        """
        if base_path is None:
            base_path = Path(__file__).parent.parent
        self.base_path = base_path
        self.loaded_models: Dict[str, Llama] = {}

    def load_model(self, model_name: str, force_reload: bool = False) -> Llama:
        """
        Load a specific model by name

        Args:
            model_name: Name of model to load (mistral, phi3, tinyllama)
            force_reload: Force reload even if already loaded

        Returns:
            Loaded Llama model instance
        """
        if model_name not in self.MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(self.MODELS.keys())}")

        # Check if already loaded
        if model_name in self.loaded_models and not force_reload:
            logger.info(f"Using cached model: {model_name}")
            return self.loaded_models[model_name]

        model_config = self.MODELS[model_name]
        model_path = self.base_path / model_config['path']

        # Check if model file exists
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found: {model_path}\n"
                f"Please download the {model_name} model to {model_path}"
            )

        logger.info(f"Loading model: {model_name} from {model_path}")
        logger.info(f"Description: {model_config['description']}")

        try:
            # Load model with configuration
            model = Llama(
                model_path=str(model_path),
                **model_config['config']
            )

            # Cache the loaded model
            self.loaded_models[model_name] = model
            logger.info(f"Model {model_name} loaded successfully")

            return model

        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise

    def load_all_models(self) -> Dict[str, Llama]:
        """
        Load all available models for comparison

        Returns:
            Dictionary of model_name -> Llama instance
        """
        models = {}

        for model_name in self.MODELS.keys():
            try:
                models[model_name] = self.load_model(model_name)
            except Exception as e:
                logger.warning(f"Could not load {model_name}: {e}")
                continue

        if not models:
            raise Exception("No models could be loaded")

        logger.info(f"Loaded {len(models)} models for comparison")
        return models

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Get information about a model

        Args:
            model_name: Name of the model

        Returns:
            Dictionary with model information
        """
        if model_name not in self.MODELS:
            raise ValueError(f"Unknown model: {model_name}")

        config = self.MODELS[model_name]
        model_path = self.base_path / config['path']

        info = {
            'name': model_name,
            'description': config['description'],
            'path': str(model_path),
            'exists': model_path.exists(),
            'config': config['config']
        }

        if model_path.exists():
            # Add file size information
            size_mb = model_path.stat().st_size / (1024 * 1024)
            info['size_mb'] = round(size_mb, 1)

        return info

    def list_available_models(self) -> Dict[str, Dict[str, Any]]:
        """
        List all available models with their status

        Returns:
            Dictionary of model information
        """
        models_info = {}

        for model_name in self.MODELS.keys():
            models_info[model_name] = self.get_model_info(model_name)

        return models_info

    def compare_models(self, query: str, max_tokens: int = 256) -> Dict[str, Dict[str, Any]]:
        """
        Run the same query on all models for comparison

        Args:
            query: Query to test on all models
            max_tokens: Maximum tokens to generate

        Returns:
            Comparison results from all models
        """
        results = {}

        for model_name, model in self.load_all_models().items():
            logger.info(f"Testing {model_name}...")

            try:
                import time
                start_time = time.time()

                # Generate response
                response = model(
                    query,
                    max_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                    stop=["Human:", "User:", "\n\n"]
                )

                elapsed_time = (time.time() - start_time) * 1000

                results[model_name] = {
                    'response': response['choices'][0]['text'].strip(),
                    'tokens_generated': response['usage']['completion_tokens'],
                    'time_ms': elapsed_time,
                    'tokens_per_second': response['usage']['completion_tokens'] / (elapsed_time / 1000)
                }

            except Exception as e:
                logger.error(f"Error with {model_name}: {e}")
                results[model_name] = {
                    'error': str(e),
                    'response': None
                }

        return results

    def unload_model(self, model_name: str):
        """
        Unload a model from memory

        Args:
            model_name: Name of model to unload
        """
        if model_name in self.loaded_models:
            del self.loaded_models[model_name]
            logger.info(f"Unloaded model: {model_name}")

    def unload_all_models(self):
        """Unload all loaded models from memory"""
        for model_name in list(self.loaded_models.keys()):
            self.unload_model(model_name)
        logger.info("All models unloaded")

    def get_recommended_model(self, criteria: str = 'balanced') -> str:
        """
        Get recommended model based on criteria

        Args:
            criteria: Selection criteria (accuracy, speed, balanced, memory)

        Returns:
            Recommended model name
        """
        recommendations = {
            'accuracy': 'mistral',     # Best accuracy
            'speed': 'tinyllama',       # Fastest
            'balanced': 'phi3',         # Good balance
            'memory': 'tinyllama'       # Lowest memory usage
        }

        return recommendations.get(criteria, 'phi3')