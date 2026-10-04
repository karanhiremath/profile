defmodule CosVoice do
  @moduledoc "Cos-voice BEAM supervisor surface."

  def status do
    %{
      supervisor: Supervisor.which_children(CosVoice.Supervisor),
      apply: CosVoice.ApplyHost.status(),
      wasm: CosVoice.Wasm.status(),
      chips: CosVoice.ChipFeed.last(),
      router: CosVoice.Router.snapshot()
    }
  end

  def route(dest, text), do: CosVoice.Router.route(dest, text)

  def s2s(dest), do: CosVoice.Router.s2s(dest)
end
