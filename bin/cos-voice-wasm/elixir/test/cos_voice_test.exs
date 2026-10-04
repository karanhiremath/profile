defmodule CosVoiceTest do
  use ExUnit.Case, async: false

  test "otp tree is up" do
    kids = Supervisor.which_children(CosVoice.Supervisor)
    ids = Enum.map(kids, fn {id, _pid, _type, _mod} -> id end)
    assert CosVoice.ApplyHost in ids
    assert CosVoice.Wasm in ids
    assert CosVoice.ChipFeed in ids
    assert CosVoice.Router in ids
  end

  test "router returns a dest plan without send-keys to cos" do
    assert {:ok, plan} = CosVoice.route("cos", "ao2 land the crate")
    assert get_in(plan, ["route", "dest"]) == "ao2"
    assert get_in(plan, ["apply", "blocked_targets"]) |> Enum.member?("cos")
  end

  test "s2s plan binds chief-of-staff and leaves loopback" do
    assert {:ok, plan} = CosVoice.s2s("cos")
    assert plan["dest"] == "cos"
    assert plan["send_keys"] == false
    assert get_in(plan, ["cartesia", "replace_loopback"]) == false
    assert get_in(plan, ["cartesia", "provider"]) == "cartesia"
    assert get_in(plan, ["profile", "name"]) in ["chief-of-staff", ""]
  end

  test "wasm component s2s does not need python when the module is loaded" do
    status = CosVoice.Wasm.status()

    if CosVoice.Wasm.component_path() do
      assert status[:status] == :ready
      assert status[:via] == :wasmex_components
      assert {:ok, plan} =
               CosVoice.Wasm.apply_map(%{
                 "op" => "s2s",
                 "dest" => "cos",
                 "yaml" =>
                   "name: chief-of-staff\ntts:\n  enabled: true\n  model: sonic-3.5\nstt:\n  enabled: true\n  model: ink-2\n"
               })

      assert plan["dest"] == "cos"
      assert get_in(plan, ["cartesia", "replace_loopback"]) == false
      assert get_in(plan, ["cartesia", "provider"]) == "cartesia"
      refute is_map_key(plan, "CARTESIA_API_KEY")
    else
      assert status[:status] == :missing
    end
  end
end
