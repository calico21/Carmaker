function varargout = cmmodelconf(varargin)
% CMEDITCONF - Edit CarMaker for Simulink model configuration parameters.
% 

% Siehe auch ccopenfcn.m in der Matlab-Installation.

if nargin >= 1
    cmd = char(varargin(1));
    switch (cmd)
	case 'get',
	    varargout(1) = { get_config(char(varargin(2))) };
	case 'edit',
	    edit_config;
	otherwise,
	    error(sprintf('unknown command "%s"', cmd));
    end
else
    error('not enough input arguments');
end


function conf = get_config (mdl)
    try
	%disp(sprintf('model=<%a>', mdl));
	block = char(find_system(mdl, 'RegExp', 'On', 'FollowLinks', 'On', 'Name', '.*Edit Model.*Configuration.*'));
	%disp(sprintf('block=<%s>', block));
	%block = char(strrep(block, sprintf('\n'), ' '));
	data = get_param(block, 'UserData');
    catch
	%disp(lasterr);
	data = [];
    end
    conf = fill_defaults(data);


function edit_config
    % Get a handle for the block in case the user changes the current
    % block (gcb) while the dialog is open.
    hand = gcbh;

    try
      data = get_param(hand, 'UserData');
    catch
      data = [];
    end
    data = fill_defaults(data);

    prompt = { ...
	'Server application name (leave empty for default)', ...
	'Command line arguments' ...
	'Environment variables (separate with "," or ";")' ...
    };
    def = {data.AppVersion, data.CmdLine, data.CmdEnv};
    lineNo = [1; 1; 1];
    title = 'CarMaker Model Configuration';
    a = inputdlg(prompt, title, lineNo, def, 'off');
    if length(a) == 0
      return; % canceled
    end

    newdataempty = 1;
    if length(a{1})
      newdata.AppVersion = a{1};
      newdataempty = 0;
    end
    if length(a{2})
      newdata.CmdLine = a{2};
      newdataempty = 0;
    end
    if length(a{3})
      newdata.CmdEnv = a{3};
      newdataempty = 0;
    end

    if newdataempty
      set_param(hand, 'UserData', []);
    else
      set_param(hand, 'UserData', newdata);
    end
    set_param(hand, 'UserDataPersistent', 'on');

    % Force Simulink to accept that the model is modified.
    param = 'Creator';
    val = get_param(bdroot, param);
    set_param(bdroot, param, [val 'xyz']);
    set_param(bdroot, param, val);



function data1 = fill_defaults (data)
    ansAppVersionEmpty = 1;
    ansCmdLineEmpty    = 1;
    ansCmdEnvEmpty     = 1;

    if length(data) 
      if isfield(data, 'AppVersion')
	data1.AppVersion = data.AppVersion;
	ansAppVersionEmpty = 0;
      end
      if isfield(data, 'CmdLine')
	data1.CmdLine = data.CmdLine;
	ansCmdLineEmpty = 0;
      end
      if isfield(data, 'CmdEnv')
	data1.CmdEnv = data.CmdEnv;
	ansCmdEnvEmpty = 0;
      end
    end

    if ansAppVersionEmpty
      data1.AppVersion = '';
    end
    if ansCmdLineEmpty
      data1.CmdLine = '';
    end
    if ansCmdEnvEmpty
      data1.CmdEnv = '';
    end

