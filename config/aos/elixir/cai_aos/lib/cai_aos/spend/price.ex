defmodule CaiAos.Spend.Price do
  @moduledoc "Classify a model id against the Cursor token-fee table."

  @calibration_fee 0.07
  @calibration_usd 1.45

  @explicit %{
    "grok-4.6:fast" => 1.45,
    "grok-4.6" => 0.68,
    "grok-4.6:slow" => 0.68
  }

  @together_buckets %{
    "deepseek-v4-flash-0731" => %{
      input: 0.14,
      output: 0.28,
      cache_read: 0.03,
      cache_write: 0.0
    }
  }

  @fee_pct %{
    "auto" => 0.04,
    "composer" => 0.04,
    "grok-4.6:fast" => 0.07,
    "grok-4.6" => 0.03,
    "grok-4.6:slow" => 0.03,
    "composer-2:fast" => 0.02,
    "composer-2" => 0.01,
    "claude-4.6-sonnet" => 0.11,
    "claude-4.5-haiku" => 0.03,
    "claude-4.6-opus" => 0.32,
    "claude-4.6-opus:fast" => 0.50,
    "gpt-5.3-codex" => 0.15,
    "gpt-5.3-codex:fast" => 0.23,
    "gpt-5.2-codex" => 0.15,
    "gpt-5.2-codex:fast" => 0.23,
    "gpt-5.4" => 0.15,
    "gpt-5.4:fast" => 0.23,
    "gpt-5.4-mini" => 0.06,
    "gpt-5.4-mini:fast" => 0.10,
    "gemini-3-pro" => 0.19,
    "gemini-3-flash" => 0.06,
    "gemini-3.1-pro" => 0.19,
    "kimi-k2.5" => 0.06
  }

  def classify(model) when is_binary(model) do
    raw = model |> String.downcase() |> String.replace("_", "-")
    bare = raw |> String.split("/") |> List.last()
    cond do
      String.contains?(raw, "deepseek-v4-flash-0731") -> "deepseek-v4-flash-0731"
      String.contains?(bare, "grok-4.6") and String.contains?(bare, "fast") -> "grok-4.6:fast"
      String.contains?(bare, "grok-4.6") -> "grok-4.6"
      Map.has_key?(@fee_pct, bare) -> bare
      String.contains?(bare, "composer-2") and String.contains?(bare, "fast") -> "composer-2:fast"
      String.contains?(bare, "composer-2") -> "composer-2"
      String.contains?(bare, "composer") -> "composer"
      true -> bare
    end
  end

  def classify(_), do: ""

  def fee_pct(id), do: Map.get(@fee_pct, id)

  def buckets(id), do: Map.get(@together_buckets, id)

  def usd_per_m(id) do
    case buckets(id) do
      %{input: rate} -> rate
      _ ->
        Map.get_lazy(@explicit, id, fn ->
          case fee_pct(id) do
            nil -> 0.0
            pct -> pct / @calibration_fee * @calibration_usd
          end
        end)
    end
  end

  def status(id) do
    cond do
      Map.has_key?(@together_buckets, id) -> "explicit"
      Map.has_key?(@explicit, id) -> "explicit"
      Map.has_key?(@fee_pct, id) -> "estimated"
      true -> "unknown"
    end
  end

  def pi_cost(id) do
    rate = usd_per_m(id)
    %{input: rate, output: rate, cacheRead: rate, cacheWrite: rate}
  end
end
