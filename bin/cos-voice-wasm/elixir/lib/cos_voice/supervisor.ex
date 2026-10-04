defmodule CosVoice.Supervisor do
  @moduledoc """
  Thin OTP tree for Cos-voice apply.

  rest_for_one: apply host, then chip feed, then dest router.
  Same module is intended for mac host and later `mac-s` / `oma-s`.
  """
  use Supervisor

  def start_link(opts), do: Supervisor.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(_opts) do
    children = [
      CosVoice.ApplyHost,
      CosVoice.Wasm,
      CosVoice.ChipFeed,
      CosVoice.Router
    ]

    Supervisor.init(children, strategy: :rest_for_one)
  end
end
