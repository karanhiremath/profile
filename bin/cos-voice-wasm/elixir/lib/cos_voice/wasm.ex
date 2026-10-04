defmodule CosVoice.Wasm do
  @moduledoc """
  Loads the Cos-voice WIT component through Wasmex.Components.

  This is the applying runtime for dest/s2s plans. Cartesia keys stay out.
  Missing component is a labeled gap; native `cos-voice-apply` remains fallback.
  """
  use GenServer
  require Logger

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def status, do: GenServer.call(__MODULE__, :status)
  def apply_json(json) when is_binary(json), do: GenServer.call(__MODULE__, {:apply_json, json}, 15_000)

  def apply_map(map) when is_map(map) do
    apply_json(JSON.encode!(map))
  end

  def component_path do
    env = System.get_env("COS_VOICE_COMPONENT")
    crate = Path.expand("../../..", __DIR__)

    candidates =
      [
        env,
        Path.join(crate, "target/wasm32-wasip2/debug/cos_voice_wasm.wasm"),
        Path.join(crate, "target/wasm32-wasip2/release/cos_voice_wasm.wasm")
      ]
      |> Enum.reject(&is_nil/1)

    Enum.find(candidates, &File.regular?/1)
  end

  @impl true
  def init(_opts) do
    case start_component() do
      {:ok, path, pid} ->
        {:ok, %{status: :ready, via: :wasmex_components, path: path, pid: pid}}

      {:error, reason} ->
        Logger.warning("cos-voice wasm component missing or failed: #{inspect(reason)}")
        {:ok, %{status: :missing, via: :none, path: component_path(), pid: nil, reason: reason}}
    end
  end

  @impl true
  def handle_call(:status, _from, state), do: {:reply, Map.delete(state, :pid), state}

  def handle_call({:apply_json, _json}, _from, %{status: :missing} = state) do
    {:reply, {:error, :component_missing}, state}
  end

  def handle_call({:apply_json, json}, _from, %{pid: pid} = state) do
    {:reply, call_apply(pid, json), state}
  end

  defp start_component do
    if Code.ensure_loaded?(Wasmex.Components) do
      case component_path() do
        nil ->
          {:error, :component_missing}

        path ->
          opts = %{
            path: path,
            wasi: struct(Wasmex.Wasi.WasiP2Options),
            name: CosVoice.Wasm.Component
          }

          case Wasmex.Components.start_link(opts) do
            {:ok, pid} -> {:ok, path, pid}
            {:error, reason} -> {:error, reason}
          end
      end
    else
      {:error, :wasmex_not_loaded}
    end
  end

  defp call_apply(pid, json) do
    result =
      Enum.find_value(
        ["apply-json", ["apply-json"], "apply_json"],
        fn name ->
          case Wasmex.Components.call_function(pid, name, [json]) do
            {:ok, out} -> {:ok, out}
            {:error, _} -> nil
          end
        end
      )

    case result do
      {:ok, out} -> decode_guest(out)
      nil -> {:error, :export_missing}
    end
  end

  defp decode_guest({:ok, payload}) when is_binary(payload), do: decode_plan(payload)
  defp decode_guest({:error, reason}), do: {:error, reason}

  defp decode_guest(payload) when is_binary(payload), do: decode_plan(payload)

  defp decode_guest(other), do: {:error, {:bad_guest, other}}

  defp decode_plan(payload) do
    case JSON.decode(payload) do
      {:ok, plan} -> {:ok, plan}
      {:error, _} -> {:error, :bad_json}
    end
  end
end
