defmodule CaiAos.Spend.Window do
  @moduledoc "Compose session + weekly spend against optional caps."

  def compose(event, windows) do
    harness = window_harness(event)
    caps = caps_for(windows, harness)
    session = to_float(Map.get(event, :session_usd) || get_in(event, [:window, :session_usd]) || 0)
    weekly = to_float(Map.get(event, :weekly_usd) || get_in(event, [:window, :weekly_usd]) || 0)
    turn = get_in(event, [:cost, :total]) || 0.0
    session_after = session + turn
    weekly_after = weekly + turn
    session_cap = caps[:session_usd]
    weekly_cap = caps[:weekly_usd]

    Map.put(event, :window, %{
      harness: harness,
      session_usd: session,
      weekly_usd: weekly,
      session_after: session_after,
      weekly_after: weekly_after,
      session_cap: session_cap,
      weekly_cap: weekly_cap,
      over_session: over?(session_after, session_cap),
      over_weekly: over?(weekly_after, weekly_cap)
    })
  end

  defp window_harness(event) do
    classified = Map.get(event, :classified) || ""
    harness = Map.get(event, :harness) || Map.get(event, "harness") || ""

    cond do
      harness in ["cursor", "claude", "codex", "together"] -> harness
      String.starts_with?(classified, "deepseek") -> "together"
      String.starts_with?(classified, "grok") -> "cursor"
      String.contains?(classified, "claude") -> "claude"
      String.contains?(classified, "codex") or String.starts_with?(classified, "gpt-") -> "codex"
      true -> harness
    end
  end

  defp caps_for(nil, _), do: %{session_usd: nil, weekly_usd: nil}

  defp caps_for(windows, harness) when is_map(windows) do
    inner =
      get_in(windows, ["windows", harness]) ||
        get_in(windows, [:windows, harness]) ||
        Map.get(windows, harness) ||
        %{}

    %{
      session_usd: Map.get(inner, "session_usd") || Map.get(inner, :session_usd),
      weekly_usd: Map.get(inner, "weekly_usd") || Map.get(inner, :weekly_usd)
    }
  end

  defp over?(_amount, nil), do: false
  defp over?(amount, cap) when is_number(cap), do: amount > cap
  defp over?(_, _), do: false

  defp to_float(n) when is_number(n), do: n * 1.0
  defp to_float(_), do: 0.0
end
