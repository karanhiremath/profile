defmodule CaiAos do
  @moduledoc "CAI-AOS BEAM surface. Spend is the first OTP app."

  def spend_status, do: CaiAos.Spend.Monitor.snapshot()

  def spend_eval(event, windows \\ nil) do
    CaiAos.Spend.evaluate(event, windows)
  end
end
