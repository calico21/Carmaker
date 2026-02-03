function cmguicmd (varargin)			% -*- Mode: Fundamental -*-
% CMGUICMD - Execute a Tcl command in the CarMaker GUI.
%
%   RESULT           = CMGUICMD(COMMAND)
%   RESULT           = CMGUICMD(COMMAND, TIMEOUT_MS)
%   [RESULT, STATUS] = CMGUICMD(COMMAND)
%   [RESULT, STATUS] = CMGUICMD(COMMAND, TIMEOUT_MS)
%
%   Sends the specified COMMAND string to the CarMaker GUI for execution in
%   the GUI's Tcl interpreter. Any Tcl statement (including all Script Control
%   commands) is allowed.
%
%   STATUS informs about success or failure during execution of COMMAND
%   and RESULT will be set appopriately. Possible values for STATUS are:
%
%      0    No error, COMMAND executed successfully.
%           RESULT contains whatever COMMAND evaluated to.
%
%     -1    A Tcl error occured during execution of COMMAND.
%     	    The resulting Tcl error message will be returned as RESULT.
%
%     -2    Connection error, COMMAND could not be sent to the CarMaker GUI.
%           RESULT will be 'connection failed' in this case.
%
%     -3    Timeout, execution of COMMAND did not complete within the
%           specified time (see below). RESULT will be set to 'timeout'.
%
%   A timeout may be specified to determine how long to wait for completion
%   of COMMAND. Possible values for TIMEOUT_MS are:
%
%      -1   Wait until completion of COMMAND.
%           This is also the default value if TIMEOUT_MS is not specified.
%
%       0   Don't wait, return immediately with an empty string as RESULT.
%
%     > 0   Wait at most the specified number of milliseconds for completion
%           of COMMAND. If COMMAND doesn't finish in time, return 'timeout'
%           as RESULT.
%
%   Be sure not to execute commands that in some way talk back to Matlab.
%   This will most likely lead to a deadlock situation, as the Matlab command
%   interpreter is blocked while executing cmguicmd.
