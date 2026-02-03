function cmread (varargin)			% -*- Mode: Fundamental -*-
% CMREAD - Load CarMaker result files into the Matlab workspace.
%
%   VAR = CMREAD([PATH] [,OPTION...] [,PATTERN])
%
%   Specifying the path:
%   o If PATH is specified and it is a file, CMREAD reads the contents
%     of the file into the workspace.
%   o If PATH is specified and it is a directory, CMREAD opens a
%     file selection dialog and lets the user choose a file.
%   o If no PATH is specified, CMREAD checks for the existence of the
%     workspace variable cmreadloc. If the variable exists, CMREAD
%     takes its value as a path specification.
%   o If no PATH is specified and no cmreadloc variable exists , the output
%     directory of the current CarMaker simulation is assumed as the directory
%     specified. (Only available in CarMaker for Simulink)
%
%   Specifying options:
%   o Currently there are no options available.
%   
%   Specifying a pattern:
%   If not all variables contained in the file are to be loaded into
%   the workspace, one or more patterns of variable names can be
%   specified. A pattern follows the syntax of Un*x shell wildcard
%   patterns, i.e. it might contain '*', '?', '[' and ']' as wildcard
%   characters.
%   
%   To specify options and/or patterns AND let CMREAD automatically
%   determine the directory, call CMREAD with an empty PATH argument,
%   e.g. like this: erg = cmread('', 'Car.*') .
%
%   After loading a result file into the workspace, VAR will contain an
%   array of structs, one for each variable. In case the user cancels the
%   file selection dialog, an empty array is returned.

