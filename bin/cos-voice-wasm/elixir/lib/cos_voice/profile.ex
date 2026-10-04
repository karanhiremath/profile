defmodule CosVoice.Profile do
  @moduledoc """
  Personal Hermes YAML only. Host-edge read; wasm never sees secrets.
  """

  @blocked ~w(chief-of-staff-work work-notes-steward cosw cos-work)

  def name_for(dest) when is_binary(dest) do
    name = dest |> String.split(":") |> hd() |> String.downcase()

    cond do
      name in @blocked or String.ends_with?(name, "-work") -> nil
      name in ~w(cos cos-voice chief chief-of-staff) -> "chief-of-staff"
      name == "notes" -> "personal-notes-steward"
      String.starts_with?(name, "personal-") -> name
      true -> nil
    end
  end

  def yaml_for(dest) do
    case name_for(dest) do
      nil ->
        nil

      name ->
        Enum.find_value(search_dirs(), fn dir ->
          path = Path.join(dir, name <> ".yaml")
          if File.regular?(path), do: File.read!(path)
        end)
    end
  end

  def search_dirs do
    extra =
      case System.get_env("COS_VOICE_PROFILE_DIR") do
        nil -> []
        dir -> [dir]
      end

    extra ++
      [
        Path.expand("~/src/hermes/profiles"),
        Path.expand("~/src/profile/bin/hermes/profiles")
      ]
  end
end
