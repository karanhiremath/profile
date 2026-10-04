defmodule CosVoice.ChipFeed do
  @moduledoc """
  Polls layer / OTEL / alert chips from the apply binary.
  Sources are `atop dump`, `~/.pi/agent/otel`, and job-bus status files.
  No second collector.
  """
  use GenServer
  require Logger

  @interval 15_000

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def last, do: GenServer.call(__MODULE__, :last)

  @impl true
  def init(_opts) do
    report = poll()
    {:ok, %{report: report, at: DateTime.utc_now()}, @interval}
  end

  @impl true
  def handle_info(:timeout, state) do
    {:noreply, %{state | report: poll(), at: DateTime.utc_now()}, @interval}
  end

  @impl true
  def handle_call(:last, _from, state), do: {:reply, state, state}

  defp poll do
    case CosVoice.ApplyHost.cmd(["chips"]) do
      {:ok, 0, out} ->
        decode(out)

      {:ok, code, out} ->
        Logger.warning("chips exit #{code}: #{String.slice(out, 0, 200)}")
        %{"error" => "chips_exit", "code" => code}

      {:error, reason} ->
        %{"error" => inspect(reason)}
    end
  end

  defp decode(out) do
    case JSON.decode(out) do
      {:ok, report} -> report
      {:error, _} -> %{"error" => "json", "raw" => String.slice(out, 0, 200)}
    end
  end
end
