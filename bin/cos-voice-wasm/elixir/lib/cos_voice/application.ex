defmodule CosVoice.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    CosVoice.Supervisor.start_link([])
  end
end
