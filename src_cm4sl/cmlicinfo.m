function cmlicinfo (varargin)			% -*- Mode: Fundamental -*-
% CMLICINFO - IPGLock licensing utility
%
%   CMLICINFO(...)
%
%   CMLICINFO prints some basic licensing information to the Matlab
%   console window.
%
%   Specifying optional arguments:
%       '-attach': Attach to the CarMaker for Simulink background service.
%
%       '-nodongle': Run the utility without dongle support.
%
%       '<modestring>': Activate debug mode, using the specified mode string.
%                Option processing stops after the mode string, so the mode
%                string should always be passed as the last option.
%
%   Examples:
%       cmlicinfo
%       cmlicinfo('-attach')
%       cmlicinfo('mac')
%