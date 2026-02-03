function cmstartmdl (varargin)		% -*- Mode: Fundamental -*-
% CMSTARTMDL - Start active CarMaker for Simulink model

% Beim letzten Start trat evtentuell ein Fehler auf, sodass in Folge dessen
% 'cmfailure' gestartet wurde und jetzt also noch aktiv ist, was aber als
% Default-Modell fuer den aktuellen Start voellig unbrauchbar ist.
% Setze zurueck auf das eigentlich zuletzt zu startende Modell.
cmcmd('activemodel', '$LASTACTIVE$');

failed = 0;
cleared = 0;
activatedmdl = '';
mdl = '';

vhcl = cmcmd('vehicleparams');

if any_fcns(vhcl)
    % Problem: Fehlerhafter Caching-Mechanismus in Matlab bis mindestens
    % R2010b fuehrt dazu, dass Aenderungen an hier aufgerufenen Skripten
    % erst mit einer Simulation Verzoegerung Wirkung zeigen.
    % Passiert nur hier, aber nicht bei direktem Aufruf in der Matlab-Konsole!?

    if length(dbstatus()) == 0
	% clear im Debug-Modus wuerde zum Loeschen aller Breakpoints fuehren...
	clear('functions');
    end
end

if ~failed
    if length(vhcl.ActivateFcn) > 0
	if execute(vhcl.ActivateFcn) == 0
	    activatedmdl = cmcmd('activemodel');
	else
	    failed = 1;
	end
    end
end
% POST: activatedmdl bestimmt.

if ~failed
    try
	close_system('cmfailure', 0);
	close_system('mmfailure', 0);
    end
    mdls = find_system('type','block_diagram', 'Lock', 'off');
    if length(activatedmdl) > 0
	if ismember(activatedmdl, mdls)
	    mdl = activatedmdl;
	else
	    set_error(sprintf('Activated Simulink model ''%s'' not loaded', activatedmdl));
	    failed = 1;
	end
    else
	mdl = choose_active_model(mdls);
	if length(mdl) > 0
	    cmcmd('activemodel', mdl);
	else
	    set_error('No Simulink model selected');
	    failed = 1;
	end
    end
end
% POST: mdl bestimmt.

if ~failed && length(vhcl.StartFcn) > 0
    if execute(vhcl.StartFcn) ~= 0
	failed = 1;
    end
end


% Simulation in jedem Fall starten,
% damit potenzielle Log-Meldungen von weiter oben im Log-File ankommen.

if failed || length(mdl) == 0
    % Dummy-Modell laden, sonst keine Simulation moeglich.
    if strcmp(cmcmd('maker'), 'MotorcycleMaker')
	mdl = 'mmfailure';
    else
	mdl = 'cmfailure';
    end
    load_system(mdl);
    cmcmd('activemodel', mdl);
else
    cmcmd('stopfcn', vhcl.StopFcn);
end
% POST: mdl enthaelt Namen eines geladenen Simulink-Modells.

% Workspace Variablen setzen bevor SimulationStatus in 'initializing' übergeht,
% damit sie sich noch auf den aktuellen Test Run auswirken.
cmcmd('setworkspacevars');

set_param(mdl, 'SimulationCommand', 'start');


function b = any_fcns (vhcl)
    b = length(vhcl.ActivateFcn)>0 || length(vhcl.StartFcn)>0 || length(vhcl.StopFcn)>0;


function mdl = choose_active_model (mdls)
    mdl = '';
    if length(mdls) == 0,
	%uiwait(msgbox('No Simulink model loaded.', 'CarMaker Error', 'modal'));
	set_error('No Simulink model loaded');
    elseif length(mdls) == 1,
	mdl = char(mdls(1));
    elseif length(mdls) > 1,
	mdl = cmcmd('activemodel');
	if length(mdl) == 0 || ~ismember(mdl, mdls)
	    mdl = '';
	    [s,v] = listdlg( ...
		'ListSize', [200 300], ...
		'PromptString', 'Select the active CarMaker model.', ...
		'SelectionMode', 'single', ...
		'ListString', mdls);
	    if v ~= 0,
		mdl = char(mdls(s));
	    end
	end
    end


function failed = execute (cmd)
% Angegebenes Kommando ausfuehren, dabei moeglichst Neuladen erzwingen.
    failed = 0;

    n = length(cmd);
    if cmd(n) == ';'
	func = cmd(1:n-1);
    else
	func = cmd;
	cmd = sprintf('%s;', cmd);	% Unnoetige Ausgabe unterdruecken.
    end

    try
	evalin('base', cmd);
    catch
	set_error(lasterr);
	failed = 1;
    end


function set_error (err)
    % Fehlermeldung wird spaeter in SimCore_TestRun_Start() ausgegeben.
    cmcmd('setstartfcnfailure', err);

