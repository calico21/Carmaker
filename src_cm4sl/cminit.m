function cminit (varargin)		% -*- Mode: Fundamental -*-
% CMINIT - Initialize CarMaker for Simulink environment.

disp('Initialize CarMaker for Simulink.');


% Special hack to prevent a DDE deadlock when starting the
% CarMaker GUI.
if ispc & isempty(which('CM_HIL'))
    script = which('cminit');
    [here,n,e] = fileparts(script);
    gui  = fullfile(here, '..', '..', 'GUI', 'HIL.exe');
    hack = fullfile(here, '..', 'cmddehack.tcl');
    cmd  = sprintf('"%s" -wish "%s"', gui, hack);
    system(cmd);
end


disp('Done.');

