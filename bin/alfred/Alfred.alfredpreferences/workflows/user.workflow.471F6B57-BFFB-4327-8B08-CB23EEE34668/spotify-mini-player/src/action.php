<?php

// Turn off all error reporting
//error_reporting(0);

require './spotify-mini-player/src/functions.php';
require_once './spotify-mini-player/vendor/phprtflite/phprtflite/lib/PHPRtfLite.php';

// Load and use David Ferguson's Workflows.php class
require_once './spotify-mini-player/src/workflows.php';
$w = new Workflows('com.vdesabou.spotify.mini.player');

$query = $argv[1];
$type = $argv[2];
$add_to_option = $argv[3];

$arg = mb_unserialize($query);

//var_dump($arg);

$track_uri = $arg[0];
$album_uri = $arg[1];
$artist_uri = $arg[2];
$playlist_uri = $arg[3];
$spotify_command = $arg[4];
$original_query = $arg[5];
$other_settings = $arg[6];
$other_action = $arg[7];
$alfred_playlist_uri = $arg[8];
$artist_name = $arg[9];
$track_name = $arg[10];
$album_name = $arg[11];
$track_artwork_path = $arg[12];
$artist_artwork_path = $arg[13];
$album_artwork_path = $arg[14];
$playlist_name = $arg[15];
$playlist_artwork_path = $arg[16];
$alfred_playlist_name = $arg[17];


if ($add_to_option != "") {
	if (file_exists($w->data() . '/update_library_in_progress')) {
		displayNotification("Error: cannot modify library while update is in progress");
		return;
	}
}

if ($other_action == "update_playlist" && $playlist_uri != "" && $playlist_name != "") {
	updatePlaylist($w, $playlist_uri, $playlist_name);
	return;
}

if ($spotify_command != "" && $type == "TRACK" && $add_to_option == "") {

	$spotify_command = str_replace("\\", "", $spotify_command);
	exec("osascript -e 'tell application \"Spotify\" to $spotify_command'");
	return;
}

	if ($type == "TRACK") {
		if ($track_uri != "") {
			if ($add_to_option != "") {

				//
				// Read settings from DB
				//
				$getSettings = 'select theme,is_alfred_playlist_active from settings';
				$dbfile = $w->data() . '/settings.db';
				exec("sqlite3 -separator '	' \"$dbfile\" \"$getSettings\" 2>&1", $settings, $returnValue);

				if ($returnValue != 0) {
					displayNotification("Error: cannot read settings");
					return;
				}

				foreach ($settings as $setting):
					$setting = explode("	", $setting);
				$theme = $setting[0];
				$is_alfred_playlist_active = $setting[1];
				endforeach;

				$tmp = explode(':', $track_uri);

				if ($track_artwork_path == "") {
					$track_artwork_path = getTrackOrAlbumArtwork($w, $theme, $track_uri, true);
				}
				if ($is_alfred_playlist_active == true) {

					if ($alfred_playlist_uri == "" || $alfred_playlist_name == "") {
						displayNotification("Error: Alfred Playlist is not set");
						return;
					}

					// add track to alfred playlist
					$ret = addTracksToPlaylist($w, $tmp[2], $alfred_playlist_uri, $alfred_playlist_name, false);
					if (is_numeric($ret) && $ret > 0) {
						displayNotificationWithArtwork('' . $track_name . ' by ' . $artist_name . ' added to ' . $alfred_playlist_name, $track_artwork_path);
						return;
					} else if (is_numeric($ret) && $ret == 0) {
							displayNotification('Error: ' . $track_name . ' by ' . $artist_name . ' is already in ' . $alfred_playlist_name);
							return;
						} else {
						return;
					}
				} else {
					// add track to your music
					$ret = addTracksToMyTracks($w, $tmp[2], false);
					if (is_numeric($ret) && $ret > 0) {
						displayNotificationWithArtwork('' . $track_name . ' by ' . $artist_name . ' added to Your Music', $track_artwork_path);
						return;
					} else if (is_numeric($ret) && $ret == 0) {
							displayNotification('Error: ' . $track_name . ' by ' . $artist_name . ' is already in Your Music');
							return;
						} else {
						return;
					}
				}
			} else if ($playlist_uri != "") {
					exec("osascript -e 'tell application \"Spotify\" to play track \"$track_uri\" in context \"$playlist_uri\"'");
					displayNotificationWithArtwork('🔈 ' . $track_name . ' by ' . ucfirst($artist_name), $track_artwork_path);
					return;
				} else {
				if ($other_action == "") {
					exec("osascript -e 'tell application \"Spotify\" to play track \"$track_uri\"'");
					displayNotificationWithArtwork('🔈 ' . $track_name . ' by ' . ucfirst($artist_name), $track_artwork_path);
					return;
				}
			}
		}
	} else if ($type == "ALBUM") {
		if ($album_uri == "") {
			// case of current song with alt
			$album_uri = getAlbumUriFromTrack($w, $track_uri);
			if ($album_uri == false) {
				displayNotification("Error: cannot get current album");
				return;
			}
			$album_artwork_path = getTrackOrAlbumArtwork($w, $theme, $album_uri, true);
		}
		exec("osascript -e 'tell application \"Spotify\" to play track \"$album_uri\"'");
		displayNotificationWithArtwork('🔈 Album ' . $album_name . ' by ' . ucfirst($artist_name), $album_artwork_path);
		return;
	} else if ($type == "ONLINE") {
		if ($artist_uri == "") {
			// case of current song with cmd
			$artist_uri = getArtistUriFromTrack($w, $track_uri);
			if ($artist_uri == false) {
				displayNotification("Error: cannot get current artist");
				return;
			}
		}

		exec("osascript -e 'tell application \"Alfred 2\" to search \"spot_mini Online▹$artist_uri@$artist_name\"'");
		return;
	}else if ($type == "RANDOM") {
		$track_uri = getRandomTrack($w);
		if ($track_uri == false) {
			displayNotification("Error: cannot find a random track");
		}
		exec("osascript -e 'tell application \"Spotify\" to play track \"$track_uri\"'");
		displayNotificationForCurrentTrack($w);
		return;
	}else if ($type == "CURRENT") {
		displayNotificationForCurrentTrack($w);
		return;
	}else if ($type == "LYRICS") {
		displayLyricsForCurrentTrack();
		return;
	}else if ($type == "CURRENT_ARTIST_RADIO") {
		createRadioArtistPlaylistForCurrentArtist($w);
		return;
	}else if ($type == "CURRENT_TRACK_RADIO") {
		createRadioSongPlaylistForCurrentTrack($w);
		return;
	}else if ($type == "KILL_UPDATE") {
		killUpdate($w);
		return;
	}else if ($type == "NEXT") {
		exec("osascript -e 'tell application \"Spotify\" to next track'");
		displayNotificationForCurrentTrack($w);
		return;
	}else if ($type == "PREVIOUS") {
		exec("osascript -e 'tell application \"Spotify\" to previous track'");
		displayNotificationForCurrentTrack($w);
		return;
	}else if ($type == "PLAY") {
		exec("osascript -e 'tell application \"Spotify\" to play'");
		displayNotificationForCurrentTrack($w);
		return;
	}else if ($type == "PAUSE") {
		exec("osascript -e 'tell application \"Spotify\" to pause'");
		return;
	}else if ($type == "UPDATE_LIBRARY") {
		if (file_exists($w->data() . '/update_library_in_progress')) {
			displayNotification("Error: cannot update library while update is in progress");
			return;
		}
		updatePlaylistList($w);
		return;
	}else if ($type == "ADD_CURRENT_TRACK") {
		addCurrentTrackToAlfredPlaylistOrMyMusic($w);
		return;
	} else if ($type == "ALBUM_OR_PLAYLIST") {
		if ($add_to_option != "") {

			if ($album_name != "") {

				//
				// Read settings from DB
				//
				$getSettings = 'select theme,is_alfred_playlist_active from settings';
				$dbfile = $w->data() . '/settings.db';
				exec("sqlite3 -separator '	' \"$dbfile\" \"$getSettings\" 2>&1", $settings, $returnValue);

				if ($returnValue != 0) {
					displayNotification("Error: cannot read settings");
					return;
				}

				foreach ($settings as $setting):
					$setting = explode("	", $setting);
				$theme = $setting[0];
				$is_alfred_playlist_active = $setting[1];
				endforeach;

				if ($album_uri == "") {
					// case of current song with shift
					$album_uri = getAlbumUriFromTrack($w, $track_uri);
					if ($album_uri == false) {
						displayNotification("Error: cannot get current album");
						return;
					}
					$album_artwork_path = getTrackOrAlbumArtwork($w, $theme, $album_uri, true);
				}

				if ($is_alfred_playlist_active == true) {

					if ($alfred_playlist_uri == "" || $alfred_playlist_name == "") {
						displayNotification("Error: Alfred Playlist is not set");
						return;
					}

					// add album to alfred playlist
					$ret = addTracksToPlaylist($w, getTheAlbumTracks($w, $album_uri), $alfred_playlist_uri, $alfred_playlist_name, false);
					if (is_numeric($ret) && $ret > 0) {
						displayNotificationWithArtwork('Album ' . $album_name . ' added to ' . $alfred_playlist_name, $album_artwork_path);
						return;
					} else if (is_numeric($ret) && $ret == 0) {
							displayNotification('Error: Album ' . $album_name . ' is already in ' . $alfred_playlist_name);
							return;
						} else {
						return;
					}
				} else {
					// add album to your music
					$ret = addTracksToMyTracks($w, getTheAlbumTracks($w, $album_uri), false);
					if (is_numeric($ret) && $ret > 0) {
						displayNotificationWithArtwork('Album ' . $album_name . ' added to Your Music', $album_artwork_path);
						return;
					} else if (is_numeric($ret) && $ret == 0) {
							displayNotification('Error: Album ' . $album_name . ' is already in Your Music');
							return;
						} else {
						return;
					}
				}

				return;
			} else if ($playlist_uri != "") {

					//
					// Read settings from DB
					//
					$getSettings = 'select theme,is_alfred_playlist_active from settings';
					$dbfile = $w->data() . '/settings.db';
					exec("sqlite3 -separator '	' \"$dbfile\" \"$getSettings\" 2>&1", $settings, $returnValue);

					if ($returnValue != 0) {
						displayNotification("Error: cannot read settings");
						return;
					}

					foreach ($settings as $setting):
						$setting = explode("	", $setting);
					$theme = $setting[0];
					$is_alfred_playlist_active = $setting[1];
					endforeach;

					$playlist_artwork_path = getPlaylistArtwork($w, $theme, $playlist_uri, true, true);

					if ($is_alfred_playlist_active == true) {
						if ($playlist_uri == $alfred_playlist_uri) {
							displayNotification("Error: cannot add Alfred Playlist " . $alfred_playlist_name . " to itself!");
							return;
						}
						// add playlist to alfred playlist
						$ret = addTracksToPlaylist($w, getThePlaylistTracks($w, $playlist_uri), $alfred_playlist_uri, $alfred_playlist_name, false);
						if (is_numeric($ret) && $ret > 0) {
							displayNotificationWithArtwork('Playlist ' . $playlist_name . ' added to ' . $alfred_playlist_name, $playlist_artwork_path);
							return;
						} else if (is_numeric($ret) && $ret == 0) {
								displayNotification('Error: Playlist ' . $playlist_name . ' is already in ' . $alfred_playlist_name);
								return;
							} else {
							return;
						}
					} else {
						// add playlist to your music
						$ret = addTracksToMyTracks($w, getThePlaylistTracks($w, $playlist_uri), false);
						if (is_numeric($ret) && $ret > 0) {
							displayNotificationWithArtwork('Playlist ' . $playlist_name . ' added to Your Music', $playlist_artwork_path);
							return;
						} else if (is_numeric($ret) && $ret == 0) {
								displayNotification('Error: Playlist ' . $playlist_name . ' is already in Your Music');
								return;
							} else {
							return;
						}
					}

					return;
				}
		}
	} else if ($type == "ARTIST") {

		if ($artist_uri == "") {
			// case of current song with cmd
			$artist_uri = getArtistUriFromTrack($w, $track_uri);
			if ($artist_uri == false) {
				displayNotification("Error: cannot get current artist");
				return;
			}
			$artist_artwork_path = getArtistArtwork($w, 'black', $artist_name, true);
		}

		exec("osascript -e 'tell application \"Spotify\" to play track \"$artist_uri\"'");
		displayNotificationWithArtwork('🔈 Artist ' . $artist_name, $artist_artwork_path);
		return;
	}

	if ($playlist_uri != "") {
		exec("osascript -e 'tell application \"Spotify\" to play track \"$playlist_uri\"'");
		displayNotificationWithArtwork('🔈 Playlist ' . $playlist_name, $playlist_artwork_path);
		return;
	} else if ($other_settings != "") {
		$setting = explode('▹', $other_settings);
		if ($setting[0] == "MAX_RESULTS") {
			$setSettings = "update settings set max_results=" . $setting[1];
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotification("Max results set to $setting[1]");
			return;
		} else if ($setting[0] == "RADIO_TRACKS") {
			$setSettings = "update settings set radio_number_tracks=" . $setting[1];
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotification("Radio track number set to $setting[1]");
			return;
		} else if ($setting[0] == "Oauth_Client_ID") {
			$setSettings = 'update settings set oauth_client_id=\"' . $setting[1] . '\"';
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotification("Client ID set to $setting[1]");
			return;
		} else if ($setting[0] == "Oauth_Client_SECRET") {
			$setSettings = 'update settings set oauth_client_secret=\"' . $setting[1] . '\"';
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotification("Client Secret set to $setting[1]");
			return;
		} else if ($setting[0] == "ALFRED_PLAYLIST") {
			$setSettings = 'update settings set alfred_playlist_uri=\"' . $setting[1] . '\"' . ',alfred_playlist_name=\"' . $setting[2] . '\"';
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");

			displayNotificationWithArtwork('Alfred Playlist set to ' . $setting[2], getPlaylistArtwork($w, 'black', $setting[1], true));
			return;

		} else if ($setting[0] == "Open_Url") {
			exec("open \"$setting[1]\"");
			return;
		} else if ($setting[0] == "CLEAR_ALFRED_PLAYLIST") {
			if ($setting[1] == "" || $setting[2] == "") {
				displayNotification("Error: Alfred Playlist is not set");
				return;
			}

			if (clearPlaylist($w, $setting[1], $setting[2])) {
				displayNotificationWithArtwork('Alfred Playlist ' . $setting[2] . ' was cleared' , getPlaylistArtwork($w, 'black', $setting[1], true));
			}
			return;
		}
	} else if ($original_query != "") {
		exec("osascript -e 'tell application \"Alfred 2\" to search \"spotifious $original_query\"'");
		return;
	} else if ($other_action != "") {

		//
		// Read settings from DB
		//
		$getSettings = 'select theme,is_alfred_playlist_active from settings';
		$dbfile = $w->data() . '/settings.db';
		exec("sqlite3 -separator '	' \"$dbfile\" \"$getSettings\" 2>&1", $settings, $returnValue);

		if ($returnValue != 0) {
			displayNotification("Error: cannot read settings");
			return;
		}

		foreach ($settings as $setting):
			$setting = explode("	", $setting);
		$theme = $setting[0];
		$is_alfred_playlist_active = $setting[1];
		endforeach;

		if ($other_action == "disable_all_playlist") {
			$setSettings = "update settings set all_playlists=0";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Search scope set to your music", './spotify-mini-player/images/' . $theme . '/' . 'search.png');
			return;
		} else if ($other_action == "enable_all_playlist") {
			$setSettings = "update settings set all_playlists=1";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Search scope set to all playlists", './spotify-mini-player/images/' . $theme . '/' . 'search.png');
			return;
		} else if ($other_action == "enable_spotifiuous") {
			$setSettings = "update settings set is_spotifious_active=1";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Spotifious is now enabled", './spotify-mini-player/images/' . $theme . '/' . 'check.png');
			return;
		} else if ($other_action == "disable_spotifiuous") {
			$setSettings = "update settings set is_spotifious_active=0";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Spotifious is now disabled", './spotify-mini-player/images/' . $theme . '/' . 'uncheck.png');
			return;
		} else if ($other_action == "set_theme_to_black") {
			$setSettings = "update settings set theme='black'";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Theme set to black", './spotify-mini-player/images/' . 'black' . '/' . 'check.png');
			return;
		} else if ($other_action == "set_theme_to_green") {
			$setSettings = "update settings set theme='green'";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Theme set to green", './spotify-mini-player/images/' . 'green' . '/' . 'check.png');
			return;
		} else if ($other_action == "set_theme_to_new") {
			$setSettings = "update settings set theme='new'";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Theme set to new", './spotify-mini-player/images/' . 'new' . '/' . 'check.png');
			return;
		} else if ($other_action == "enable_lyrics") {
			$setSettings = "update settings set is_lyrics_active=1";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Get Lyrics is now enabled", './spotify-mini-player/images/' . $theme . '/' . 'check.png');
			return;
		} else if ($other_action == "disable_lyrics") {
			$setSettings = "update settings set is_lyrics_active=0";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Get Lyrics is now disabled", './spotify-mini-player/images/' . $theme . '/' . 'uncheck.png');
			return;
		} else if ($other_action == "enable_alfred_playlist") {
			$setSettings = "update settings set is_alfred_playlist_active=1";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Alfred Playlist is now enabled", './spotify-mini-player/images/' . $theme . '/' . 'check.png');
			return;
		} else if ($other_action == "disable_alfred_playlist") {
			$setSettings = "update settings set is_alfred_playlist_active=0";
			$dbfile = $w->data() . "/settings.db";
			exec("sqlite3 \"$dbfile\" \"$setSettings\"");
			displayNotificationWithArtwork("Alfred Playlist is now disabled", './spotify-mini-player/images/' . $theme . '/' . 'uncheck.png');
			return;
		} else if ($other_action == "play") {
			exec("osascript -e 'tell application \"Spotify\" to play'");
			displayNotificationForCurrentTrack($w);
			return;
		} else if ($other_action == "pause") {
			exec("osascript -e 'tell application \"Spotify\" to pause'");
			return;
		} else if ($other_action == "kill_update") {
			killUpdate($w);
			return;
		} else if ($other_action == "lyrics") {
			displayLyricsForCurrentTrack();
			return;
		} else if ($other_action == "current_track_radio") {
			createRadioSongPlaylistForCurrentTrack($w);
			return;
		} else if ($other_action == "Oauth_Login") {
			$cache_log=$w->cache() . '/spotify_mini_player_web_server.log';
			exec("php -S localhost:15298 > \"$cache_log\" 2>&1 &");
			sleep(2);
			exec("open http://localhost:15298");
				return;
		} else if ($other_action == "check_for_update") {
			if (! $w->internet()) {
				displayNotificationWithArtwork("Error: No internet connection", './spotify-mini-player/images/warning.png');
				return;
			}

			$dbfile = $w->data() . '/settings.db';

			try {
				$dbsettings = new PDO("sqlite:$dbfile", "", "", array(PDO::ATTR_PERSISTENT => true));
				$dbsettings->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
			} catch (PDOException $e) {
				handleDbIssuePdoEcho($dbsettings);
				$dbsettings=null;
				return;
			}
			$check_results = checkForUpdate($w, 0, $dbsettings);
			if ($check_results != null && is_array($check_results)) {
				displayNotificationWithArtwork('New version ' . $check_results[0] . ' is available in Downloads directory ', './spotify-mini-player/images/' . $theme . '/' . 'check_update.png');
			}
			else if ($check_results == null) {
					displayNotificationWithArtwork('No update available', './spotify-mini-player/images/' . $theme . '/' . 'check_update.png');
				}
			return;
		} else if ($other_action == "current") {
			displayNotificationForCurrentTrack($w);
			return;
		} else if ($other_action == "add_current_track") {
			if ($is_alfred_playlist_active == true) {
				addCurrentTrackToAlfredPlaylist($w);
			} else {
				addCurrentTrackToMyTracks($w);
			}
			return;
		} else if ($other_action == "previous") {
			exec("osascript -e 'tell application \"Spotify\" to previous track'");
			displayNotificationForCurrentTrack($w);
			return;
		} else if ($other_action == "next") {
			exec("osascript -e 'tell application \"Spotify\" to next track'");
			displayNotificationForCurrentTrack($w);
			return;
		} else if ($other_action == "add_current_track") {
			addCurrentTrackToAlfredPlaylistOrMyMusic($w);
			return;
		} else if ($other_action == "random") {
			$track_uri = getRandomTrack($w);
			if ($track_uri == false) {
				displayNotification("Error: cannot find a random track");
				return;
			}
			exec("osascript -e 'tell application \"Spotify\" to play track \"$track_uri\"'");
			displayNotificationForCurrentTrack($w);
			return;
		} else if (startsWith($other_action, 'display_biography')) {

			$json = doWebApiRequest($w, 'http://developer.echonest.com/api/v4/artist/biographies?api_key=5EG94BIZEGFEY9AL9&id=' . $artist_uri);
			$response = $json->response;
			PHPRtfLite::registerAutoloader();

			foreach ($response->biographies as $biography) {

				if ($biography->site == "wikipedia") {
					$wikipedia = $biography->text;
				}
				if ($biography->site == "last.fm") {
					$lastfm = $biography->text;
				}
				$default = 'Source: ' . $biography->site . '\n' . $biography->text;
			}

			if ($wikipedia) {
				$text = $wikipedia;
				$artist = $artist_name . ' (Source: Wikipedia)';
			} elseif ($lastfm) {
				$text = $lastfm;
				$artist = $artist_name . ' (Source: Last.FM)';
			} else {
				$text = $default;
				$artist = $artist_name . ' (Source: ' . $biography->site . ')';
			}
			if ($text=="") {
				$text = "No biography found";
				$artist = $artist_name;
			}
			$output=strip_tags($text);

			$file = $w->cache() . '/biography.rtf';

			$rtf = new PHPRtfLite();

			$section = $rtf->addSection();
			// centered text
			$fontTitle = new PHPRtfLite_Font(28, 'Arial', '#000000', '#FFFFFF');
			$parFormatTitle = new PHPRtfLite_ParFormat(PHPRtfLite_ParFormat::TEXT_ALIGN_CENTER);
			$section->writeText($artist, $fontTitle, $parFormatTitle);

			$parFormat = new PHPRtfLite_ParFormat();
			$parFormat->setSpaceAfter(4);
			$font = new PHPRtfLite_Font(14, 'Arial', '#000000', '#FFFFFF');
			// write text
			$section->writeText($output, $font, $parFormat);

			$rtf->save($file);
			if ($other_action == 'display_biography') {
				exec("qlmanage -p \"$file\";osascript -e 'tell application \"Alfred 2\" to search \"spot_mini Artist▹" . $artist_uri . "∙" . $artist_name . "▹\"'");
			} else {
				exec("qlmanage -p \"$file\";osascript -e 'tell application \"Alfred 2\" to search \"spot_mini Online▹" . $artist_uri . "@" . $artist_name . "\"'");
			}
			return;

		} else if ($other_action == "morefromthisartist") {

			if (! $w->internet()) {
				displayNotificationWithArtwork("Error: No internet connection", './spotify-mini-player/images/warning.png');
				return;
			}
			if ($artist_uri == "") {
				$artist_uri = getArtistUriFromTrack($w, $track_uri);
			}
			exec("osascript -e 'tell application \"Alfred 2\" to search \"spot_mini Online▹" . $artist_uri . "@" . escapeQuery($artist_name) . "\"'");
		} else if ($other_action == "playartist") {
			exec("osascript -e 'tell application \"Spotify\" to play track \"$artist_uri\"'");
			displayNotificationWithArtwork('🔈 Artist ' . $artist_name, $artist_artwork_path);
			return;
		} else if ($other_action == "playalbum") {
			if ($album_uri == "") {
				$album_uri = getAlbumUriFromTrack($w, $track_uri);
			}
			exec("osascript -e 'tell application \"Spotify\" to play track \"$album_uri\"'");
			displayNotificationWithArtwork('🔈 Album ' . $album_name, $album_artwork_path);
			return;
		} else if ($other_action == "radio_artist") {
				createRadioArtistPlaylist($w, $artist_name);
				return;
		} else if ($other_action == "update_library") {
				updateLibrary($w);
				return;
		} else if ($other_action == "update_your_music") {
			updateMyMusic($w);
			return;
		} else if ($other_action == "update_playlist_list") {
			updatePlaylistList($w);
			return;
		}
	}
?>
