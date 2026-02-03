function cmblockmagic (which)
% Update model blocks automagically.

try
    switch (which)
	case 'gui_copy',
	    cb_gui_copy(gcbh);
	case 'gui_fix_display',
	    cb_gui_fix_display(gcbh);
	otherwise,
	    ;
    end
catch
    disp(sprintf('cmblockmagic: %s', gcb));
    disp(sprintf('       error: %s', lasterr));
end


function cb_gui_copy (h)
    %disp('cb_gui_copy');

    set_param(h, 'LinkStatus', 'none');		% Break library link

    % CopyFcn wird jetzt im Moment gerade ausgefuehrt, auf dem Weg vom
    % Blockset ins Modell, soll danach aber nie mehr ausgefuehrt werden.
    set_param(h, 'CopyFcn', '');

    % LoadFcn soll in jedem Modell dafuer sorgen, dass cmenv ablaeuft.
    set_param(h, 'LoadFcn', 'if ~length(which(''cmself'')), cmenv; end');

    % OpenFcn soll in jedem Modell dafuer sorgen, dass bei Bedarf einmalig
    % (CM-Upgrade) die Optik der 3 Hauptbloecke (Config, Blockset, GUI)
    % aktualisiert wird und danach der GUI-Block seine Optik und Funktion
    % behaelt.
    name = get_param(h, 'Name');
    if     ~isempty(strfind(name, 'Motorcycle'))
	code = 'cmblockmagic(''gui_fix_display''); MM_Simulink';
    elseif ~isempty(strfind(name, 'Truck'))
	code = 'cmblockmagic(''gui_fix_display''); TM_Simulink';
    else
	code = 'cmblockmagic(''gui_fix_display''); CM_Simulink';
    end
    set_param(h, 'OpenFcn', code);

    fix_size(h, 64, 64);
    set_param(h, 'ShowName',   'on');
    set_param(h, 'DropShadow', 'off');


function cb_gui_fix_display (h)
    %disp('cb_gui_fix_display');

    fix_size(h, 64, 64);
    set_param(h, 'ShowName',   'on');
    set_param(h, 'DropShadow', 'off');


function fix_size (h, width, height)
    pos = get_param(h, 'Position');
    if pos(3)-pos(1)~=width || pos(4)-pos(2)~=height
	newpos = [pos(1) pos(2) pos(1)+width pos(2)+height];
	set_param(h, 'Position', newpos);
    end

