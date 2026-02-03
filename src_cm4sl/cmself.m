function d = cmself ()				% -*- Mode: Fundamental -*-
% CMSELF - Returns its own installation directory.

    [d, n, e] = fileparts(which('cmself'));
