defmodule CosVoice.Router do
  @moduledoc """
  Routes Cos-voice dests as functional effects.

  This process only asks the apply host for a plan. It does not send-keys
  into Cos or Atop. Worker input-buffer remains an explicit later effect.
  """
  use GenServer

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def route(dest, text), do: GenServer.call(__MODULE__, {:route, dest, text}, 15_000)
  def s2s(dest), do: GenServer.call(__MODULE__, {:s2s, dest}, 15_000)
  def snapshot, do: GenServer.call(__MODULE__, :snapshot)

  @impl true
  def init(_opts), do: {:ok, %{last: nil}}

  @impl true
  def handle_call({:route, dest, text}, _from, state) do
    result =
      case CosVoice.ApplyHost.cmd(["route", "--dest", dest, "--text", text]) do
        {:ok, 0, out} ->
          case JSON.decode(out) do
            {:ok, plan} -> {:ok, plan}
            {:error, _} -> {:error, :bad_json}
          end

        {:ok, _code, out} ->
          {:error, out}

        {:error, reason} ->
          {:error, reason}
      end

    {:reply, result, %{state | last: result}}
  end

  def handle_call({:s2s, dest}, _from, state) do
    result =
      case CosVoice.Wasm.apply_map(s2s_payload(dest)) do
        {:ok, plan} -> {:ok, Map.put(plan, "via", "wasmex-components")}
        {:error, _} -> decode_cmd(["s2s", "--dest", dest])
      end

    {:reply, result, %{state | last: result}}
  end

  def handle_call(:snapshot, _from, state) do
    {:reply,
     %{
       apply: CosVoice.ApplyHost.status(),
       chips: CosVoice.ChipFeed.last(),
       last_route: state.last
     }, state}
  end

  defp s2s_payload(dest) do
    base = %{"op" => "s2s", "dest" => dest}

    case CosVoice.Profile.yaml_for(dest) do
      nil -> base
      yaml -> Map.put(base, "yaml", yaml)
    end
  end

  defp decode_cmd(args) do
    case CosVoice.ApplyHost.cmd(args) do
      {:ok, 0, out} ->
        case JSON.decode(out) do
          {:ok, plan} -> {:ok, plan}
          {:error, _} -> {:error, :bad_json}
        end

      {:ok, _code, out} ->
        {:error, out}

      {:error, reason} ->
        {:error, reason}
    end
  end
end
