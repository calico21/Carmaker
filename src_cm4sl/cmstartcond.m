function sc = cmstartcond (fname)
% CMSTARTCOND - Read CarMaker start conditions into a workspace variable.
%
% SC = CMSTARTCOND(FILENAME) read the start conditions stored in the
% specified vehicle file into the workspace variable SC.
%
% Read start conditions from the vehicle parameter file:
% Recommended Callback function:
%    File / Model Properties / Callbacks (Model initialization function)
%    [[ Block Properties / Callbacks (InitFcn) ]]
% Callback statement:
%    sc = cmstartcond('../Data/Vehicle/DemoCar')
%
% In block parameters of your model, you may then use fields of the variable
% sc for initialization before a simulation begins.

    ifilecmd('clearlog');

    ifid = ifilecmd('new');
    notok = ifilecmd('read', ifid, fname);
    if notok
	entries = ifilecmd('getlog');
	error(char(entries(1)));
    end

    sc = read_conditions(ifid);

    show_log(['Warnings while reading ' fname ':']);

    ifilecmd('delete', ifid);



function sc = read_conditions (ifid)

    sc.Fr1.t_0   = getvec(ifid, 'VhclStartCond.Fr1.t_0',   3);
    sc.Fr1.r_zyx = getvec(ifid, 'VhclStartCond.Fr1.r_zyx', 3);
    sc.Fr1.v_0   = getvec(ifid, 'VhclStartCond.Fr1.v_0',   3);

    sc.SuspFL = read_Susp (ifid, 'FL');
    %sc.TFL   = read_Tire (ifid, 'FL');
    %sc.WFL   = read_Wheel(ifid, 'FL');

    sc.SuspFR = read_Susp (ifid, 'FR');
    %sc.TFR   = read_Tire (ifid, 'FR');
    %sc.WFR   = read_Wheel(ifid, 'FR');

    sc.SuspRL = read_Susp (ifid, 'RL');
    %sc.TRL   = read_Tire (ifid, 'RL');
    %sc.WRL   = read_Wheel(ifid, 'RL');

    sc.SuspRR = read_Susp (ifid, 'RR');
    %sc.TRR   = read_Tire (ifid, 'RR');
    %sc.WRR   = read_Wheel(ifid, 'RR');



function susp = read_Susp (ifid, pos)
    susp.q             = getvec(ifid, ...
				['VhclStartCond.Susp' pos '.q'], 2);
    susp.Spring.Frc    = ifilecmd('getnum', ifid, ...
				['VhclStartCond.Susp' pos '.Spring.Frc'], 0);
    susp.Spring.l      = ifilecmd('getnum', ifid, ...
				['VhclStartCond.Susp' pos '.Spring.l'], 0);



%function t = read_Tire (ifid, pos)
%    t.Frc_W            = getvec(ifid, ...
%				['VhclStartCond.T' pos '.Frc_W'], 3);
%    t.Radius           = ifilecmd('getnum', ifid, ...
%				['VhclStartCond.T' pos '.Radius'], 0);



%function w = read_Wheel (ifid, pos)
%    w.active           = ifilecmd('getnum', ifid, ...
%				['VhclStartCond.W' pos '.active'], 0);
%    w.rotv             = ifilecmd('getnum', ifid, ...
%				['VhclStartCond.W' pos '.rotv'], 0);



function v = getvec (ifid, key, n)
    [v, notok] = ifilecmd('gettab', ifid, key, 1, zeros(1, n));
    if notok
	v = zeros(1, n);
    elseif length(v) < n
	v(length(v)+1:n) = zeros(1, n-length(v));
    elseif length(v) > n
	v = v(1:n);
    end



function show_log (msg)
    if ifilecmd('logsize', 'all') & length(msg),
	disp(msg);
    end
    entries = ifilecmd('getlog');
    for i=1:length(entries)
	disp(char(entries(i)));
    end

