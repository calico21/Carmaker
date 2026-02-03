function cmstopeng		    % Mode: -*- Fundamental -*-
% CMSTOPENG - Stop CarMaker for Simulink engine background task

    t = timerfind('Name', 'CMEng');
    if length(t) > 0
	stop(t);
	delete(t);
    end
    cmcmd engrunning 0;
