function cmstop (varargin)		% -*- Mode: Fundamental -*-
% CMSTOP - Stop active CarMaker for Simulink model

mdl = cmcmd('runningmodel');
mdls = find_system('type','block_diagram');

if length(mdl) > 0 & ismember(mdl, mdls),
    set_param(mdl, 'SimulationCommand', 'stop');
end

