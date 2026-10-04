defmodule CosVoice.ApplyHost do
  @moduledoc """
  Supervises the Rust apply binary (`cos-voice-apply`).
  Does not send-keys. Missing binary is a labeled gap, not a crash loop.
  """
  use GenServer
  require Logger

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)

  def status, do: GenServer.call(__MODULE__, :status)
  def cmd(args), do: GenServer.call(__MODULE__, {:cmd, args}, 15_000)

  @impl true
  def init(_opts) do
    bin = apply_bin()
    status = if bin && File.regular?(bin), do: :ready, else: :missing
    if status == :missing do
      Logger.warning("cos-voice-apply missing; rust stub not built yet (#{inspect(bin)})")
    end
    {:ok, %{bin: bin, status: status}}
  end

  @impl true
  def handle_call(:status, _from, state), do: {:reply, state, state}

  def handle_call({:cmd, args}, _from, %{bin: bin, status: :ready} = state) do
    {out, code} = System.cmd(bin, args, stderr_to_stdout: true)
    {:reply, {:ok, code, out}, state}
  end

  def handle_call({:cmd, _args}, _from, state) do
    {:reply, {:error, :apply_missing}, state}
  end

  def apply_bin do
    env = System.get_env("COS_VOICE_APPLY")
    crate = Path.expand("../../../target/debug/cos-voice-apply", __DIR__)

    cond do
      is_binary(env) and File.regular?(env) -> env
      File.regular?(crate) -> crate
      true -> System.find_executable("cos-voice-apply")
    end
  end
end
