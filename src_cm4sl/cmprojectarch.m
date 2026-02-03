function arch = cmprojectarch
% CMPROJECTARCH - Determine (last used) target architecture of current project
%                 directory.

arch = cmprojectparam('Project', 'Target.Arch');
if length(arch) == 0
    model = bdroot();
    if length(model) ~= 0
	% Check system target file
	stf = get_param(model, 'RTWSystemTargetFile');
	if strcmp(stf, 'dsrt.tlc')
	    arch = 'dsrt';
	end
    end
end
if length(arch) == 0
    % Fallback: Frontend architecture.
    if ispc
	arch = 'win64';
    else
	arch = 'linux64';
    end
end
