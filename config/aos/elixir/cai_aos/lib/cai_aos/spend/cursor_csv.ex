defmodule CaiAos.Spend.CursorCsv do
  @moduledoc """
  Partition Cursor dashboard usage-events CSV rows.

  Cost/Kind `Free` is included quota, not zero spend.
  """

  @in_w "Input (w/ Cache Write)"
  @in_wo "Input (w/o Cache Write)"
  @cache "Cache Read"
  @out "Output Tokens"
  @total "Total Tokens"

  def partition(row) when is_map(row) do
    in_wo = num(Map.get(row, @in_wo) || Map.get(row, :input_wo))
    in_w = num(Map.get(row, @in_w) || Map.get(row, :input_w))
    cache_read = num(Map.get(row, @cache) || Map.get(row, :cache_read))
    output = num(Map.get(row, @out) || Map.get(row, :output))
    cache_write = max(0, in_w - in_wo)
    billed = num(Map.get(row, @total) || Map.get(row, :billed))
    billed = if billed > 0, do: billed, else: in_wo + output + cache_read + cache_write

    %{
      model: Map.get(row, "Model") || Map.get(row, :model) || "",
      input: in_wo,
      output: output,
      cache_read: cache_read,
      cache_write: cache_write,
      billed: billed
    }
  end

  def evaluate(row, windows \\ nil) do
    row
    |> partition()
    |> CaiAos.Spend.evaluate(windows)
  end

  defp num(nil), do: 0
  defp num("Free"), do: 0
  defp num(n) when is_number(n), do: trunc(n)

  defp num(bin) when is_binary(bin) do
    bin
    |> String.replace(",", "")
    |> String.replace("$", "")
    |> String.trim()
    |> case do
      "" -> 0
      "Free" -> 0
      other ->
        case Integer.parse(other) do
          {i, _} -> i
          :error ->
            case Float.parse(other) do
              {f, _} -> trunc(f)
              :error -> 0
            end
        end
    end
  end
end
