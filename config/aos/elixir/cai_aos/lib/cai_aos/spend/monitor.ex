defmodule CaiAos.Spend.Monitor do
  @moduledoc "GenServer accumulator. Pure eval stays in CaiAos.Spend."
  use GenServer

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def snapshot, do: GenServer.call(__MODULE__, :snapshot)
  def record(event), do: GenServer.call(__MODULE__, {:record, event})

  @impl true
  def init(_opts), do: {:ok, %{last: nil, events: 0, usd: 0.0}}

  @impl true
  def handle_call(:snapshot, _from, state), do: {:reply, state, state}

  def handle_call({:record, event}, _from, state) do
    result = CaiAos.Spend.evaluate(event)
    next = %{
      last: result,
      events: state.events + 1,
      usd: state.usd + (get_in(result, [:cost, :total]) || 0.0)
    }
    {:reply, result, next}
  end
end
