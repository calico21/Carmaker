function CarMaker_make_rtw_hook(hookMethod, modelName, rtwRoot, templateMakefile, buildOpts, buildArgs)

% If appropriately named (i.e. <target>_make_rtw_hook.m), this script will be
% invoked automatically during build. See also model parameter 'ProcessScript'
% in cmPluginModel.m.

mdlRefTargetType = get_param(modelName,'ModelReferenceTargetType');
isModelRefTarget = ~strcmp(mdlRefTargetType, 'NONE'); % NONE, SIM, or RTW

switch hookMethod
    case 'entry'
	disp(sprintf('\nCarMaker Plug-in Model Target\n'));

    case 'before_tlc'
	if ~isModelRefTarget
	    cmfixLibIdent(pwd, modelName, templateMakefile);
	end

    case 'before_make'
	% Check if this is a referenced model
	if ~isModelRefTarget
	    wrapperType = get_param(modelName, 'HilWrapperType');
	    if ~isempty(strfind(lower(templateMakefile), 'carmaker'))
		vehicleType = get_param(modelName, 'HilVehicleType');
	    else
		% The RTMaker target does not have this parameter.
		vehicleType = 'Car';
	    end
	    cmcpwrap(pwd, modelName, templateMakefile, wrapperType, vehicleType);
	else
	    % code that is specific to the referenced model
	end

    otherwise
	%disp(['hookMethod=', hookMethod]);
	;
end

