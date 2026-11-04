"""Models under test, how each is called, and prices (USD per million tokens) for cost accounting.

Settings follow each provider's API defaults where they exist, with reasoning on and medium effort where it is
configurable, so that every model reasons before acting (as in agent harnesses). Prices: list prices on 2026-11-04
(OpenRouter listing; Anthropic per the API reference). OpenRouter calls are billed from the returned usage.cost.
"""

MODELS = {
    # key: provider, model id, settings, prices (input, cache write, cache read, output)
    # Claude through OpenRouter, pinned to Anthropic's standard endpoint (the Anthropic API account had no credit left);
    # prompt caching via a cache_control breakpoint on the newest message.
    "opus-5.5": dict(provider="openrouter", model="anthropic/claude-opus-5.5", effort="medium", anthropic_route=True,
                     prices=(4.0, 5.0, 0.20, 20.0)),
    "fable-5.1": dict(provider="openrouter", model="anthropic/claude-fable-5.1", effort="medium", anthropic_route=True,
                      prices=(10.0, 12.5, 0.25, 50.0)),
    # GPT-6 started on the OpenAI API; that account ran out of credit mid-run (4 Nov), so the rest (and reruns) go
    # through OpenRouter pinned to OpenAI as the serving provider.
    "gpt-6-sol": dict(provider="openrouter", model="openai/gpt-6-sol", effort="medium", or_only=["openai"],
                      prices=(2.0, 2.0, 0.20, 10.0)),
    "gpt-6-astra": dict(provider="openrouter", model="openai/gpt-6-astra", effort="medium", or_only=["openai"],
                        prices=(10.0, 10.0, 1.00, 50.0)),
    "gemini-3.8-flash": dict(provider="openrouter", model="google/gemini-3.8-flash", effort="medium",
                             prices=(0.83, 0.83, 0.083, 4.12)),
    "grok-4.7": dict(provider="openrouter", model="x-ai/grok-4.7", effort="medium", prices=(2.0, 2.0, 0.50, 6.0)),
    "deepseek-v4-pro": dict(provider="openrouter", model="deepseek/deepseek-v4-pro", effort="medium",
                            prices=(1.60, 1.60, 0.135, 3.20), vision=False),
    "kimi-k3": dict(provider="openrouter", model="moonshotai/kimi-k3", effort="medium", prices=(0.20, 0.20, 0.19, 16.0)),
    "muse-spark-1.3": dict(provider="openrouter", model="meta/muse-spark-1.3", effort="medium",
                           prices=(1.25, 1.25, 0.15, 4.25)),
    # cheap models for harness tests only
    "gemini-3.1-flash-lite": dict(provider="openrouter", model="google/gemini-3.1-flash-lite", effort="low",
                                  prices=(0.25, 0.25, 0.025, 1.50)),
    # judge
    "judge-sonnet-5.5": dict(provider="openrouter", model="anthropic/claude-sonnet-5.5", effort="low", anthropic_route=True,
                             prices=(2.0, 2.5, 0.10, 10.0)),
}

# CheatBench (Phan et al. 2026, arXiv 2609.36308) overall cheating rates, Table 2 / Figure 1, provider harnesses.
CHEATBENCH_OVERALL = {"opus-5.5": 11, "muse-spark-1.3": 39, "fable-5.1": 46, "gpt-6-astra": 47, "kimi-k3": 70,
                      "gpt-6-sol": 72, "deepseek-v4-pro": 75, "gemini-3.8-flash": 75, "grok-4.7": 78}

MAIN_MODELS = ["opus-5.5", "fable-5.1", "gpt-6-sol", "gpt-6-astra", "gemini-3.8-flash", "grok-4.7", "deepseek-v4-pro",
               "kimi-k3", "muse-spark-1.3"]
