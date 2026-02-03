function res = rmainfinit (fname, modelname)	% -*- Mode: Fundamental -*-
% RMAINFINIT - Creates <model>_rma.info file.
%
% This function creates the <model>_rma.info file with:
% - defined and used external data dictionary quantities
% - model parameters obtained from CarMaker model
% If the file already exists (previous build), it will be reset and overwritten.
%
% Returns:
%  >  0 on success (current version - value of key 'Version')
%    -1 on error

try
    if isfile(fname)
	prinf = ifile_new;
	ifile_read(prinf, fname);
	vers = ifile_getnum(prinf, 'Version');
	if isempty(vers)
	    vers = 0;
	end
	vers = vers + 1;
	ifile_delete(prinf);
    else
	vers = 1
    end
catch
    vers = 1;
end

try
    prinf = ifile_new;
    ifile_setstr(prinf, 'FileIdent', 'CarMaker-Quantities 1');
    itxt = [ ...
	cellstr(sprintf('External Quantities provided and used by %s', modelname)); ...
	cellstr('Parameters obtained from CarMaker model') ];
    ifile_settxt(prinf, 'Description', cellstr(itxt));
    ifile_setstr(prinf, 'Model', modelname);
    ifile_setstr(prinf, 'Version', vers);
    ifile_write(prinf, fname);
    res = int32(vers);
catch
    res = -1;
end

if length(prinf) > 0
    ifile_delete(prinf);
end
