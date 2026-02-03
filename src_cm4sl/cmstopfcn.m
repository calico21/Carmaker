function cmstopfcn		% -*- Mode: Fundamental -*-
% CMSTOPFCN - Execute command as defined via the CM4SL.StopFcn
% vehicle parameter.

cmd = cmcmd('stopfcn');
if length(cmd) > 0
    try
	evalin('base', cmd);
    catch
	disp(sprintf('CM4SL.StopFcn: %s\n', lasterr));
    end
end

