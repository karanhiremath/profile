defmodule CaiAos.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    CaiAos.Supervisor.start_link([])
  end
end
