function cmcmd (varargin)			% -*- Mode: Fundamental -*-
% CMCMD - Issue a CarMaker internal command.
%
%   CMCMD(CMD [,OPTION...])
%
%   The following values for CMD are officially supported:
%
%   version
%     Print the version number of CarMaker for Simulink.
%   startgui    [testrun]
%   startgui_mm [testrun]
%   startgui_tm [testrun]
%     Start the CarMaker GUI. If specified, automatically load a Test Run.
%     CarMaker for Simulink will be started first, if needed.
%   running
%     Return 1 if CarMaker for Simulink is up and running, 0 otherwise.
%   getprojectdir (deprecated: projectdir / guidir)
%     Return the current project directory of the CarMaker GUI.
%   setprojectdir
%     Switch the CarMaker GUI's project directory to Matlab's current directory.
%   activemodel [model]
%     Return the name of currently active CarMaker model.
%     If specified, set the currently active CarMaker model.
%   runningmodel
%     Return the name of currently running CarMaker model.
%   simstate
%     Return the current simulation state of the active CarMaker model.
%   endstatus
%     Returns 'failed', 'aborted', 'completed' or an empty string
%     indicating how the simulation ended.
%   getenv name
%     Return the value of the specified environment variable.
%   setenv name value
%     Sets the specified environment variable to the specified value.
%   exit
%     Immediately quit Matlab (no proper cleanup at exit).
%     This might be used as a last resort, if Matlab's quit and exit
%     commands fail for some reason. Under Unix, this might leave the
%     terminal in a funny condition, since Matlab will not be able to
%     able to restore the terminal properly.

