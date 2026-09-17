defmodule CaiAos.Supervisor do
  @moduledoc "rest_for_one: price table, then spend monitor."
  use Supervisor

  def start_link(opts), do: Supervisor.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(_opts) do
    children = [CaiAos.Spend.Monitor]
    Supervisor.init(children, strategy: :rest_for_one)
  end
end
