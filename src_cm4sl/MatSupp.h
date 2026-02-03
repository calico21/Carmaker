/*
 ******************************************************************************
 *  CarMaker - Virtual Test Driving
 *
 *  Copyright ©1998-2025 IPG Automotive GmbH. All rights reserved.
 *  www.ipg-automotive.com
 ******************************************************************************
 */

#ifndef __MATSUPP_H__
#define __MATSUPP_H__

#if !defined(__GNUC__)
# if !defined(__attribute__)
#  define __attribute__(x)     /* nothing */
# endif
#endif

#include "infoc.h"				/* Needed because of enum. */

#include <DataDict.h>
#ifndef RTMAKER
# include <Vehicle/MBSUtils.h>
#endif

#ifdef __cplusplus
# define __MATSUPP_CPP_BEGIN      extern "C" {
# define __MATSUPP_CPP_END        }
__MATSUPP_CPP_BEGIN
#endif


#define MATSUPP_VARNAME_TMP(m,n)	m ## _for_ ## n
#define MATSUPP_VARNAME(m,n)		MATSUPP_VARNAME_TMP(m,n)


/** CarMaker target run-time library ******************************************/

void MatSupp_Init (void);


typedef struct tMatSuppSampling {
    int OverSampFac;
    int UnderSampFac;
    int UnderSampCount;
} tMatSuppSampling;

/* Determine sampling parameters of a model (0=ok, !=0 failure). */
int MatSupp_Sampling (tMatSuppSampling *sampling, double dtapp, double dtmodel);


/** Dictionary block utility functions ****************************************/

/* Compatibility with CarMaker <= 3.5 */
#define tMatSuppDictDef tQuantEntry

void MatSupp_DeclQuants  (tQuantEntry *defs);
void MatSupp_ResetQuants (tQuantEntry *defs);


/** Tunable parameter interface ***********************************************/

#if MATSUPP_NUMVER < 70000
#define tMatSuppMMI         ModelMappingInfo_tag
#else
#define tMatSuppMMI rtwCAPI_ModelMappingInfo_tag
#endif
struct tMatSuppMMI;

typedef struct tMatSuppTunables tMatSuppTunables;


/*
 * Begin/end tuning parameters of the model.
 * A handle to be used in subsequent parameter tuning operations is returned.
 *
 * In case the model has no tunable parameters, a NULL pointer is returned.
 *
 * Normally you don't have to invoke these functions directly since a
 * handle is automatically provided in the models' XXX_SetParam() function.
 */
tMatSuppTunables *MatSupp_TunBegin (const char *model,
				    const struct tMatSuppMMI *mmi);
void MatSupp_TunEnd (tMatSuppTunables *tuns);


/*
 * Return the names of all tunable parameters of a model in a list.
 * The list is NULL-terminated. If pcount is non-NULL, the number of
 * items in the list will be stored at the specified location.
 *
 * After use the list and its members must be free()'ed by the caller
 * (alternatively use InfoFreeTxt()).
 *
 * In case the model has no tunable parameters, an empty NULL-terminated
 * list is returned.
 */
char **MatSupp_TunListAll (const tMatSuppTunables *tuns, int *pcount);


/*
 * Read a tunable parameter's value from an Info File.
 * In case the name of a struct parameter is passed, the value of all
 * struct members will be read from the Info File.
 *
 * If successful, 0 is returned. In case of any error, -1 is returned and
 * an error message will be issued to the CarMaker log.
 */
int MatSupp_TunRead (const tMatSuppTunables *tuns,
		     const char *param,
		     const struct tInfos *inf, const char *key);


/*
 * Read a tunable parameter's value from an Info File.
 * If for any reason the value cannot be set from the Info File entry,
 * the provided default value is used instead. A default value of NULL
 * means to keep the parameter's original value.
 *
 * If successful, 0 is returned. In case of an error, -1 is returned and
 * an error message will be issued to the CarMaker log.
 */
int MatSupp_TunReadDef (const tMatSuppTunables *tuns,
			const char *param,
			const struct tInfos *inf, const char *key,
			const struct tInfoMat *def);


/*
 * Read all tunable parameters from an Info File.
 *
 * Each parameter's name is used as the key to lookup the Info File entry.
 * Optionally a prefix (e.g. the model name) can be prepended to the
 * name - e.g. if the name is 'kappa' and the prefix is 'SuperABS',
 * the required Info File key will be 'SuperABS.kappa'. A keyprefix
 * of NULL or "" means "no prefix".
 *
 * MatSupp_TunReadAll() requires entries for all parameters to be present
 * in the Info File. If an entry can not be read an error message will be
 * issued to the CarMaker log. The function returns the number of parameters
 * that could not be read.
 *
 * MatSupp_TunReadAllOpt() tries to read all parameters from the Info File,
 * but existence of an Info File entry for a parameter is considered optional
 * and will not lead to an error.
 *
 * See also MatSupp_TunReadDef().
 */
int MatSupp_TunReadAll (const tMatSuppTunables *tuns,
			const struct tInfos *inf, const char *keyprefix);
void MatSupp_TunReadAllOpt (const tMatSuppTunables *tuns,
			    const struct tInfos *inf, const char *keyprefix);


/*
 * Read a parameter's value.
 *
 * MatSupp_TunGetDblVec() will return a copy of the parameter's data,
 * converted to type double. The caller must free() the array.
 *
 * MatSupp_TunGetMat() will return a freshly allocated tInfoMat struct
 * which must later be free()'d by the caller.
 *
 * In case of an error a NULL pointer is returned and an error message
 * will be issued to the CarMaker log (except for MatSupp_TunGetDbl(),
 * which will return 0.0, i.e. an error cannot be detected);
 */
double MatSupp_TunGetDbl (const tMatSuppTunables *tuns,
			  const char *param);
double *MatSupp_TunGetDblVec (const tMatSuppTunables *tuns,
			      const char *param, int *nvalues);
struct tInfoMat *MatSupp_TunGetMat (const tMatSuppTunables *tuns,
				    const char *param);


/*
 * Set a parameter's value.
 *
 * If successful, 0 is returned. In case of an error -1 is returned and
 * an error message will be issued to the CarMaker log.
 */
int MatSupp_TunSetFromDbl (const tMatSuppTunables *tuns,
			   const char *param,
			   double value);
int MatSupp_TunSetFromDblVec (const tMatSuppTunables *tuns,
			      const char *param,
			      int nvalues, const double *values);
int MatSupp_TunSetFromMat (const tMatSuppTunables *tuns,
			   const char *param,
			   const struct tInfoMat *value);


/*
 * Make a tunable parameter a CarMaker quantity.
 *
 * Convenience functions for quickly adding a tunable parameter to the
 * CarMaker dictionary. Only scalar parameters are allowed. The quantity will
 * be defined as analog, non-monotonic using DDefXXX() and can be given
 * a name different from that of the parameter.
 *
 * The 'type' argument serves as an aid when the function is called with
 * 'tuns' == NULL. It must match the tunable parameter's internal type
 * (e.g. INFOMAT_DOUBLE).
 *
 * The 'place' argument specifies the DVA access point for the quantity.
 * The older function MatSupp_TunDDictDefScalar() lacks this parameter and
 * implicitly uses DVA_IO_In as the DVA access point.
 *
 * This function should only be used in the DeclParameterQuants() function
 * in a Simulink model's wrapper module.
 *
 * If successful, 0 is returned. In case of an error, -1 is returned and
 * an error message will be issued to the CarMaker log.
 */
int MatSupp_TunDDictDefScalar2 (struct tMatSuppTunables *tuns,
				const char *param, tInfoMatType type,
				const char *name, const char *unit,
				tDVAPlace place);
int MatSupp_TunDDictDefScalar (struct tMatSuppTunables *tuns,
			       const char *param, tInfoMatType type,
			       const char *name, const char *unit);


/*
 * Get the address of a scalar parameter's real part.
 *
 * This function is intended as a supplement to MatSupp_TunDDictDefScalar()
 * when a parameter quantity needs to be defined with more refined attributes.
 * The function's return value can be used as an input to any of the
 * DDictDefXXX() functions and will always be non-NULL.
 *
 * See the description of MatSupp_TunDDictDefScalar() for details.
 */
void *MatSupp_TunScalarRealAddr (struct tMatSuppTunables *tuns,
				 const char *param,
				 tInfoMatType type);



/******************************************************************************/

#ifdef __cplusplus
__MATSUPP_CPP_END
#endif

#endif /* __MATSUPP_H__ */

