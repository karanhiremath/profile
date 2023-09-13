# encoding: utf-8
=begin
I18n support for desktop application.

Copyright (C) 2008 Andrey “A.I.” Sitnik <andrey@sitnik.ru>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
=end

require 'r18n-core'

require 'pathname'
dir = Pathname(__FILE__).dirname.expand_path + 'r18n-desktop'
if /cygwin|mingw|win32/ =~ RUBY_PLATFORM
  require dir.join('win32').to_s
elsif /java/ =~ RUBY_PLATFORM
  require dir.join('java').to_s
elsif /darwin/ =~ RUBY_PLATFORM
  require dir.join('osx').to_s
else
  require dir.join('posix').to_s
end

module R18n
  class << self
    # Get user locale from system environment and load I18n object with locale
    # information and translations from +translations_places+. If user set
    # locale +manual+ put it as last argument.
    def from_env(translations_places = nil, manual = nil)
      locales  = Array(R18n::I18n.system_locale)
      locales.insert(0, ENV['LANG']) if ENV['LANG']
      locales.insert(0, manual)      if manual
      self.set I18n.new(locales, translations_places)
    end
  end
end
