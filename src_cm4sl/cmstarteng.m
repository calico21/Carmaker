function b = cmstarteng		% Mode: -*- Fundamental -*-
% CMSTARTENG - Start CarMaker for Simulink engine background task

    currentdir = pwd;
    try
	start_timer_eng;
	b = 0;
    catch
	disp(lasterr);

	disp('Warning: CarMaker command engine task could not be started');
	disp('         CarMaker will be fully functional, but can only start');
	disp('         a simulation in Simulink. The CarMaker GUI''s start/stop');
	disp('         buttons, Model Check, Driver Adaption, ScriptControl');
	disp('         etc. won''t work');
	b = 1;
    end
    cd(currentdir);


function start_timer_eng
% Start engine task using the timers of Matlab 6.5 and later versions.

    % Delete existing timer.
    cmstopeng

    % Start new timer.
    t = timer;
    set(t, 'Name',          'CMEng');
    set(t, 'ExecutionMode', 'fixedSpacing');
    set(t, 'BusyMode',      'drop');
    set(t, 'StartDelay',    1);		% avoid poll with engrunning==0
    set(t, 'Period',        0.1);	% 10 Hz
    set(t, 'TimerFcn',      'cmcmd(''timerpoll'')');
    start(t);
    cmcmd engrunning 1;
