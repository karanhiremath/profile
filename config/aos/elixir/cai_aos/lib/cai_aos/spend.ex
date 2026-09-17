defmodule CaiAos.Spend do
  @moduledoc """
  Functional spend pipeline.

  classify → partition → price → compose windows → gate.
  Do not treat Cursor SDK `$0` as free.
  """

  alias CaiAos.Spend.{Price, Window}

  def evaluate(event, windows \\ nil) do
    event
    |> classify()
    |> partition()
    |> price()
    |> Window.compose(windows)
    |> gate()
  end

  def classify(event) when is_map(event) do
    model = Map.get(event, :model) || Map.get(event, "model") || ""
    Map.merge(event_to_atom_map(event), %{model: model, classified: Price.classify(model)})
  end

  def partition(event) do
    input = token(event, :input)
    output = token(event, :output)
    cache_read = token(event, :cache_read)
    cache_write = token(event, :cache_write)

    billed =
      case Map.get(event, :billed) do
        n when is_integer(n) and n > 0 -> n
        _ -> input + output + cache_read + cache_write
      end

    Map.put(event, :tokens, %{
      input: input,
      output: output,
      cache_read: cache_read,
      cache_write: cache_write,
      billed: billed
    })
  end

  def price(event) do
    tokens = event.tokens

    cost =
      case Price.buckets(event.classified) do
        %{input: in_r, output: out_r, cache_read: read_r, cache_write: write_r} ->
          input = tokens.input * in_r / 1_000_000.0
          output = tokens.output * out_r / 1_000_000.0
          cache_read = tokens.cache_read * read_r / 1_000_000.0
          cache_write = tokens.cache_write * write_r / 1_000_000.0

          %{
            usd_per_m: %{input: in_r, output: out_r, cache_read: read_r, cache_write: write_r},
            fee_pct: nil,
            status: Price.status(event.classified),
            input: input,
            output: output,
            cache_read: cache_read,
            cache_write: cache_write,
            total: input + output + cache_read + cache_write
          }

        _ ->
          rate = Price.usd_per_m(event.classified)
          per = rate / 1_000_000.0

          %{
            usd_per_m: rate,
            fee_pct: Price.fee_pct(event.classified),
            status: Price.status(event.classified),
            input: tokens.input * per,
            output: tokens.output * per,
            cache_read: tokens.cache_read * per,
            cache_write: tokens.cache_write * per,
            total: tokens.billed * per
          }
      end

    Map.put(event, :cost, cost)
  end

  def gate(event) do
    verdict =
      cond do
        event.window.over_session -> "no-go"
        event.window.over_weekly -> "no-go"
        event.cost.status == "unknown" -> "needs-check"
        true -> "go"
      end

    Map.put(event, :gate, verdict)
  end

  defp token(event, key) do
    tokens = Map.get(event, :tokens)
    raw = if is_map(tokens), do: Map.get(tokens, key), else: nil
    raw = raw || Map.get(event, key) || Map.get(event, Atom.to_string(key)) || 0
    max(0, trunc(raw))
  end

  defp event_to_atom_map(event) do
    Map.new(event, fn
      {k, v} when is_atom(k) -> {k, v}
      {k, v} when is_binary(k) -> {String.to_atom(k), v}
      {k, v} -> {k, v}
    end)
  end
end
