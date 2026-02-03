function cmupdatemask(blk, type, par)

    if strcmp(type, 'RadarRSI')
        %% parameters of block 'Radar RSI'
        % 1) xname
        % 2) xmaxdetects
        % 3) xouttype
        % 4) xnVRx
        % 5) xstime
    
        enabled = get_param(blk, 'MaskEnables');
        value   = get_param(blk, 'MaskValues');
    
        if strcmp(par, 'xouttype')
    
            % enable xnVRx if xouttype equals 'VRx'
            switch value{3}
                case 'VRx'
                    enabled{4} = 'on';
                otherwise
                    enabled{4} = 'off';
            end
    
            % apply changes
            set_param(blk, 'MaskEnables', enabled);
    
        end
    
    elseif strcmp(type, "ReadCMParameter")
        %% parameters of block 'Read CM Parameter'
        if (strcmp(par, "set_fileid"))
            maskObj  = Simulink.Mask.get(blk);
            type     = maskObj.getParameter('xfile_type');
            fileid   = maskObj.getParameter('xfile');
    
            [instance, kind] = get_InstanceAndKindByType(maskObj, type.Value);
    
            fileid_str = get_fileid(type, instance, kind);
            
            set_param(blk,'xfile',fileid_str);
            fileid.Value = fileid_str; % duplicated logic to avoid problems with R2021a/b
    
        elseif (strcmp(par, "init"))
            maskObj  = Simulink.Mask.get(blk);
            type     = maskObj.getParameter('xfile_type');
            fileid_str   = get_param(blk,'xfile');

            % fix old spelling
            if (strcmp(fileid_str, 'Testrun'))
                fileid_str = 'TestRun';
            end

            [instance, kind] = get_InstanceAndKindByType(maskObj, type.Value);
    
            fileid_str_upd = get_fileid(type, instance, kind);
            if (~strcmp(fileid_str, fileid_str_upd))
                % Inconsistent information in mask found for fileid vs. type,
                % kind and instance.
                % Either model from previous release is openend or model was
                % manipulated without using the mask.
                % Try to set type, instance and kind to match the fileid if possible.  
                
                [instance_vehicle, kind_vehicle] = get_InstanceAndKindByType(maskObj, "Vehicle");
                [instance_trailer, kind_trailer] = get_InstanceAndKindByType(maskObj, "Trailer");
                [instance_general, kind_general] = get_InstanceAndKindByType(maskObj, "General");
    
                % TrailerX / TrX
                s = regexp(fileid_str,'(?<token_type>(Trailer|Tr))(?<token_instance>[0-9]*)(?<token_kind>[\w]*)','names');
                if (~isempty(s) && strcmp(s.token_type,"Trailer"))
                    % Trailer, Trailer2, ...
                    type.Value = "Trailer";
                    kind_trailer.Value = "Trailer";
                    if (strcmp(s.token_instance, ""))
                        s.token_instance = "1";
                    end
                    % check if trailer instance is in valid range
                    if (isempty(find(strcmp(instance_trailer.TypeOptions,s.token_instance),1)))
                        set_defaultfileid(maskObj);
                        return;
                    end
                    instance_trailer.Value = s.token_instance;
                    return;
                end
                if (~isempty(s) && strcmp(s.token_type,"Tr"))
                    type.Value = "Trailer";
                    % check if kind is available in options
                    if (isempty(find(strcmp(kind_trailer.TypeOptions,s.token_kind),1)))
                        set_defaultfileid(maskObj);
                        return;
                    end
                    kind_trailer.Value = s.token_kind;
                    if (strcmp(s.token_instance, ""))
                        s.token_instance = "1";
                    end
                    % check if trailer instance is in valid range
                    if (isempty(find(strcmp(instance_trailer.TypeOptions,s.token_instance),1)))
                        set_defaultfileid(maskObj);
                        return;
                    end
                    instance_trailer.Value = s.token_instance;
                    return;
                end
    
                % General Parameters or other Vehicle parameters
                s = regexp(fileid_str,'(?<token_kind>[\w]*)','names');
                instance_vehicle.Value = "-";
                instance_general.Value = "-";
    
                % Search General parameters
                if (~isempty(s) && ~isempty(find(strcmp(kind_general.TypeOptions,s.token_kind),1)))
                    type.Value = "General";
                    kind_general.Value = s.token_kind;
                    return;
                end
    
                % search Vehicle parameters
                if (~isempty(s) && ~isempty(find(strcmp(kind_vehicle.TypeOptions,s.token_kind),1)))
                    type.Value = "Vehicle";
                    kind_vehicle.Value = s.token_kind;
                    return;
                end
    
                % Default: Vehicle:
                set_defaultfileid(maskObj);
                return;
            end
    
        elseif (strcmp(par, "update_TypeOptions"))
            maskObj  = Simulink.Mask.get(blk);
            type     = maskObj.getParameter('xfile_type');
    
            [instance_vehicle, kind_vehicle] = get_InstanceAndKindByType(maskObj, "Vehicle");
            [instance_trailer, kind_trailer] = get_InstanceAndKindByType(maskObj, "Trailer");
            [instance_general, kind_general] = get_InstanceAndKindByType(maskObj, "General");
    
            switch type.Value
                case "Vehicle"
                    instance_vehicle.Visible = 'on';
                    kind_vehicle.Visible     = 'on';
                    instance_trailer.Visible = 'off';
                    kind_trailer.Visible     = 'off';
                    instance_general.Visible = 'off';
                    kind_general.Visible     = 'off';
                case "Trailer"
                    instance_vehicle.Visible = 'off';
                    kind_vehicle.Visible     = 'off';
                    instance_trailer.Visible = 'on';
                    kind_trailer.Visible     = 'on';
                    instance_general.Visible = 'off';
                    kind_general.Visible     = 'off';
                otherwise %General
                    instance_vehicle.Visible = 'off';
                    kind_vehicle.Visible     = 'off';
                    instance_trailer.Visible = 'off';
                    kind_trailer.Visible     = 'off';
                    instance_general.Visible = 'on';
                    kind_general.Visible     = 'on';
            end
        else
            % undefined par
        end
        % nothing to be added here, early returns!
    end

    function [FullFileName] = get_fileid(type, instance, kind)
        % combine mask parameters to get fileid
        switch type.Value
            case "Vehicle"
                FullFileName = strcat(kind.Value);
            case "General"
                FullFileName = strcat(kind.Value);
            case "Trailer"
                if (strcmp(kind.Value,"Trailer"))
                    % Special case Trailer, Trailer1...
                    if (strcmp(instance.Value, "1"))
                        FullFileName = strcat("Trailer");
                    else
                        FullFileName = strcat("Trailer", instance.Value);
                    end
                else
                    % Tr*, Tr2*,...
                    if (strcmp(instance.Value, "1"))
                        FullFileName = strcat("Tr", kind.Value);
                    else
                        FullFileName = strcat("Tr", instance.Value, kind.Value);
                    end
                end
            otherwise %Default
                FullFileName = "Vehicle"; % default
        end
        % warning('(END)  fileid: %s (%s, %s, %s)', FullFileName, type.Value, instance.Value, kind.Value);
    end


    function [instance, kind] = get_InstanceAndKindByType(maskObj, type)
        switch type
            case "Vehicle"
                instance = maskObj.getParameter('xfile_instance_vehicle');
                kind     = maskObj.getParameter('xfile_kind_vehicle');
            case "Trailer"
                instance = maskObj.getParameter('xfile_instance_trailer');
                kind     = maskObj.getParameter('xfile_kind_trailer');
            otherwise %"General"
                instance = maskObj.getParameter('xfile_instance_general');
                kind     = maskObj.getParameter('xfile_kind_general');
        end
    end

    function set_defaultfileid(maskObj)
        % issue warning
        warning(['Invalid ''Parameter location'' (xfile=''%s'') found when initializing "%s".\n' ...
                'I will use xfile=''Vehicle'' as fallback ''Parameter location''.'], ...
                maskObj.getParameter('xfile').Value, blk);
        % set default 
        set_param(blk,'xfile_type',"Vehicle");
        set_param(blk,'xfile_instance_vehicle',"-");
        set_param(blk,'xfile_kind_vehicle',"Vehicle");
        set_param(blk,'xfile',"Vehicle");
    end
end
