function res = rmainfsetstr (fname, key, str)	% -*- Mode: Fundamental -*-
% RMAINFSETSTR - Set string key in <model>_rma.info file.
%
% This function writes a string key to the <model>_rma.info file.
%
% Returns:
%     0 on success
%    -1 on error

try
    prinf = ifile_new;
    ifile_read(prinf, fname);
    ifile_setstr(prinf, key, cmcmd('uenc2str', str));
    ifile_write(prinf, fname);
    res = 0;
catch
    res = -1;
end

if length(prinf) > 0
    ifile_delete(prinf);
end
