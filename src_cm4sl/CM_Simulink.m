function CM_Simulink (varargin)		% -*- Mode: Fundamental -*-
% CM_Simulink - Start CarMaker for Simulink GUI.

if nargin == 0
    cmcmd('startgui');
else
    cmcmd('startgui', char(varargin(1)));
end
cmcmd('activemodel', gcs);

