# Allegro PCB Editor 17.4 — SKILL function index

**861 distinct `axl*` functions**, extracted from the SKILL reference
that ships with the install at `<CDS_ROOT>/doc/algroskill/`.

Generated so functions can be *looked up* rather than guessed. Guessing a
SKILL function or method name has repeatedly cost crashed sessions on this
project; the local HTML reference is authoritative and offline.

Each function links to the chapter that documents it — open the HTML file
in that folder for the full signature and description.

## Quick reference — high-value groups

**Transactions (safe writes)** (5)

- `axlDBTransactionCommit` — Database Transaction Functions
- `axlDBTransactionMark` — Database Transaction Functions
- `axlDBTransactionOops` — Database Transaction Functions
- `axlDBTransactionRollback` — Database Transaction Functions
- `axlDBTransactionStart` — Database Transaction Functions

**Reports** (2)

- `axlReportGenerate` — Reports and Extract Functions
- `axlReportRegister` — Reports and Extract Functions

**Native command shell** (2)

- `axlShell` — Allegro PCB Editor Command Shell Functions
- `axlShellPost` — Allegro PCB Editor Command Shell Functions

**Constraints (CNS)** (73)

- `axlCNSAssemblyModeGet` — IC Packaging Commands
- `axlCNSAssemblyModeSet` — IC Packaging Commands
- `axlCNSCreate` — Constraint Management Functions
- `axlCNSCsetLock` — Constraint Management Functions
- `axlCNSDFAExport` — Constraint Management Functions
- `axlCNSDFAImport` — Constraint Management Functions
- `axlCNSDFAMode` — Constraint Management Functions
- `axlCNSDelete` — Constraint Management Functions
- `axlCNSDesignGetValue` — Constraint Management Functions
- `axlCNSDesignModeGet` — Constraint Management Functions
- `axlCNSDesignModeSet` — Constraint Management Functions
- `axlCNSDesignValueCheck` — Constraint Management Functions
- `axlCNSDesignValueGet` — Constraint Management Functions
- `axlCNSDesignValueSet` — Constraint Management Functions
- `axlCNSEcseValueGet` — Constraint Management Functions
- `axlCNSEcsetCreate` — Constraint Management Functions
- `axlCNSEcsetDelete` — Constraint Management Functions
- `axlCNSEcsetGet` — Constraint Management Functions
- `axlCNSEcsetModeGet` — Constraint Management Functions
- `axlCNSEcsetModeSet` — Constraint Management Functions
- `axlCNSEcsetValueCheck` — Constraint Management Functions
- `axlCNSEcsetValueGet` — Constraint Management Functions
- `axlCNSEcsetValueSet` — Constraint Management Functions
- `axlCNSGetAssembly` — IC Packaging Commands
- …and 49 more

**Layers** (38)

- `axlChangeLayer` — IC Packaging Commands
- `axlConductorBottomLayer` — Parameter Management Functions
- `axlConductorTopLayer` — Parameter Management Functions
- `axlDBGetLayerType` — Parameter Management Functions
- `axlDBIsBondingWireLayer` — IC Packaging Commands
- `axlDBIsDieStackLayer` — IC Packaging Commands
- `axlDeleteByLayer` — Database Miscellaneous Functions
- `axlGetActiveLayer` — Design Control Functions
- `axlGetExternalLayers` — Parameter Management Functions
- `axlGetMetalUsageForLayer` — IC Packaging Commands
- `axlImpdedanceGetLayerBroadsideDPImp` — Database Miscellaneous Functions
- `axlImpdedanceGetLayerBroadsideDPWidth` — Database Miscellaneous Functions
- `axlImpdedanceGetLayerEdgeDPImp` — Database Miscellaneous Functions
- `axlImpdedanceGetLayerEdgeDPSpacing` — Database Miscellaneous Functions
- `axlImpdedanceGetLayerEdgeDPWidth` — Database Miscellaneous Functions
- `axlIsEtchLayer` — Parameter Management Functions
- `axlIsLayer` — Parameter Management Functions
- `axlIsLayerNegative` — Database Read Functions
- `axlIsVisibleLayer` — Parameter Management Functions
- `axlLayerCreateCrossSection` — Parameter Management Functions
- `axlLayerCreateNonConductor` — Parameter Management Functions
- `axlLayerDelete` — Parameter Management Functions
- `axlLayerExternal` — Parameter Management Functions
- `axlLayerGet` — Introduction to Allegro PCB Editor SKILL Functions
- …and 14 more

**DRC** (7)

- `axlDBCreateExternalDRC` — Database Create Functions
- `axlDRCGetCount` — Constraint Management Functions
- `axlDRCItem` — Constraint Management Functions
- `axlDRCUpdate` — Constraint Management Functions
- `axlDRCWaive` — Constraint Management Functions
- `axlDRCWaiveGetCount` — Constraint Management Functions
- `axlPackageDesignCheckDrcError` — IC Packaging Commands

## Full index by chapter

### `01ovrvew.html` — Introduction to Allegro PCB Editor SKILL Functions

2 functions

`axlGetParm` `axlLayerGet` 

### `02dbdesc.html` — The Allegro PCB Editor Database User Model

8 functions

`axlColorGet` `axlDBControl` `axlDBGetDesign` `axlDBGetPad` `axlDBIsFixed` `axlGetParam` `axlPadFigureTypes` `axlSetParam` 

### `03dbcre8.html` — Database Create Functions

52 functions

`axlCreateBondFinger` `axlCreateBondWire` `axlCreateWirebondGuide` `axlDB2Path` `axlDBActiveShape` `axlDBAddProp` `axlDBCreateCircle` `axlDBCreateCloseShape` `axlDBCreateExternalDRC` `axlDBCreateFillet` `axlDBCreateLine` `axlDBCreateOpenShape` `axlDBCreatePath` `axlDBCreatePin` `axlDBCreatePropDictEntry` `axlDBCreateRectangle` `axlDBCreateShape` `axlDBCreateSymbol` `axlDBCreateSymbolAutosilk` `axlDBCreateSymbolSkeleton` `axlDBCreateText` `axlDBCreateVia` `axlDBCreateViaStructure` `axlDBCreateVoid` `axlDBCreateVoidCircle` `axlDBCreateZone` `axlDBGetConnect` `axlDBGetPropDictEntry` `axlDBOpenShape` `axlDebug` `axlEnterBox` `axlEnterPath` `axlLoadPadstack` `axlLoadSymbol` `axlPadstackToDisk` `axlPathArcAngle` `axlPathArcCenter` `axlPathArcRadius` `axlPathGetLastPathSeg` `axlPathGetPathSegs` `axlPathGetWidth` `axlPathLine` `axlPathOffset` `axlPathSegGetArcCenter` `axlPathSegGetArcClockwise` `axlPathSegGetEndPoint` `axlPathSegGetWidth` `axlPathStart` `axlPathStartCircle` `axlPolyFromDB` `axlRefreshSymbol` `axlZoneCreate` 

### `04parmgt.html` — Parameter Management Functions

84 functions

`axlAddSelectAll` `axlCVFColorChooserDlg` `axlClasses` `axlClearObjectCustomColor` `axlColorLoad` `axlColorOnGet` `axlColorPriorityGet` `axlColorPrioritySet` `axlColorSave` `axlColorSet` `axlColorShadowGet` `axlColorShadowSet` `axlConductorBottomLayer` `axlConductorTopLayer` `axlCustomColorObject` `axlDBCreateFilmRec` `axlDBGetLayerType` `axlDBGetTextBlockCount` `axlDBGridGet` `axlDBGridSet` `axlDBTextBlockCreate` `axlDBTextBlockFindName` `axlDBTextBlockGetName` `axlDBTextBlockName` `axlDBTextBlockSetName` `axlDeleteObject` `axlExportXmlDBRecords` `axlFilmCreate` `axlGetExternalLayers` `axlGetSelSet` `axlGetXSection` `axlImportXmlDBRecords` `axlIsCustomColored` `axlIsEtchLayer` `axlIsLayer` `axlIsParamType` `axlIsVisibleLayer` `axlLayerCreateCrossSection` `axlLayerCreateNonConductor` `axlLayerDelete` `axlLayerExternal` `axlLayerPriorityClearAll` `axlLayerPriorityGet` `axlLayerPriorityRestoreAll` `axlLayerPrioritySaveAll` `axlLayerPrioritySet` `axlLayerSet` `axlLayerViaLabel` `axlMapClassName` `axlMaterialGet` `axlMiniStatusReset` `axlOpenDesign` `axlPadSuppressGet` `axlPadSuppressOkLayer` `axlPadSuppressSet` `axlPrintDbid` `axlSelect` `axlSetFindFilter` `axlSetPlaneType` `axlSleep` `axlSubclassRoute` `axlSubclasses` `axlUIWUpdate` `axlVisibileSet` `axlVisibleDesign` `axlVisibleGet` `axlVisibleLayer` `axlVisibleSet` `axlVisibleUpdate` `axlXSectionAssign` `axlXSectionCopy` `axlXSectionCreate` `axlXSectionCreateStackup` `axlXSectionDelete` `axlXSectionDeleteStackup` `axlXSectionGet` `axlXSectionLayerFunctions` `axlXSectionLayerTypes` `axlXSectionModify` `axlXSectionRemove` `axlXSectionRename` `axlXSectionSet` `axlcolorOnSet` `axllsParamType` 

### `05selfnd.html` — Selection and Find Functions

34 functions

`axlAddSelectBox` `axlAddSelectName` `axlAddSelectObject` `axlAddSelectPoint` `axlAutoOpenFindFilter` `axlClearSelSet` `axlCloseFindFilter` `axlDBFindByName` `axlEnterPoint` `axlFindFilterIsOpen` `axlGetFindFilter` `axlGetFindfilter` `axlGetSelSetCount` `axlLastPick` `axlLastPickIsSnapped` `axlOpenFindFilter` `axlSelectByName` `axlSelectByProperty` `axlShowObject` `axlSingleSelectBox` `axlSingleSelectName` `axlSingleSelectObject` `axlSingleSelectPoint` `axlSnapDisableAtRMB` `axlSnapEnableAtRMB` `axlSnapToObject` `axlSubSelectAll` `axlSubSelectBox` `axlSubSelectName` `axlSubSelectObject` `axlSubSelectPoint` `axlTransformObject` `axlUIPopupDefine` `axlUIPopupSet` 

### `06intedt.html` — Interactive Edit Functions

50 functions

`axlAddTaper` `axlBondFingerDelete` `axlBondWireDelete` `axlChangeLine2Cline` `axlChangeLineFont` `axlChangeWidth` `axlCopyObject` `axlCopyProperties` `axlDBAltOrigin` `axlDBChangeText` `axlDBConnectItem` `axlDBCreatePadStack` `axlDBDeleteProp` `axlDBDeletePropAll` `axlDBDeletePropDictEntry` `axlDBconnectItem` `axlDeleteFillet` `axlDeleteTaper` `axlFillet` `axlFilletConvert` `axlGetLastEnterPoint` `axlPadUserMaskLayers` `axlPadstackEdit` `axlPadstackSetType` `axlPadstackUsageTypes` `axlPolyExpand` `axlPurgePadstack` `axlPurgePadstacks` `axlReplacePadstack` `axlShapeAutoVoid` `axlShapeChangeDynamicType` `axlShapeDeleteVoids` `axlShapeDynamicUpdate` `axlShapeMerge` `axlShapeRaisePriority` `axlShoveItems` `axlShoveSetParams` `axlSmoothDesign` `axlSmoothItems` `axlSmoothSetParams` `axlStepDelete` `axlStepSet` `axlSymbolAttach` `axlSymbolDetach` `axlTextOrientationCopy` `axlWindowBoxGet` `axlWindowBoxSet` `axlZoneAccess` `axlZoneDelete` `axlZoneSet` 

### `07dbaccs.html` — Database Read Functions

33 functions

`axlAltSymbolList` `axlAltSymbolOK` `axlAltSymbolReplace` `axlBackdrillGet` `axlDBDynamicShapes` `axlDBGetAttachedText` `axlDBGetDesignUnits` `axlDBGetLonelyBranches` `axlDBGetPropDict` `axlDBGetProperties` `axlDBGetShapes` `axlDBIsBondpad` `axlDBIsBondwire` `axlDBIsPackagePin` `axlDBRefreshId` `axlDBTextBlockCompact` `axlDBViaStack` `axlGetModuleInstanceDefinition` `axlGetModuleInstanceLocation` `axlGetModuleInstanceLogicMethod` `axlGetModuleInstanceMethod` `axlGetModuleInstanceNetExceptions` `axlIsDBIDType` `axlIsDummyNet` `axlIsLayerNegative` `axlIsPinUnused` `axlIsitFill` `axlOK2Void` `axlSelectByname` `axlShapeArea` `axlStepGet` `axlStepMappedInstance` `axlViaZLength` 

### `08intprm.html` — Allegro PCB Editor Interface Functions

38 functions

`axlAddSimpleMoveDynamics` `axlAddSimpleRbandDynamics` `axlCancelEnterFun` `axlClearDynamics` `axlControlRaise` `axlDehighlightObject` `axlDesignFlip` `axlDrawObject` `axlDynamicsObject` `axlEnterAngle` `axlEnterEvent` `axlEnterString` `axlEraseObject` `axlEventSetStartPopup` `axlFinishEnterFun` `axlGetDynamicsSegs` `axlGetLineLock` `axlGetTrapBox` `axlHighlightObject` `axlMakeDynamicsPath` `axlMiniStatusLoad` `axlMyCancel` `axlMyDone` `axlRatsnestBlank` `axlRatsnestDisplay` `axlSetDynamicsMirror` `axlSetDynamicsRotation` `axlShowObjectToFile` `axlUICmdPopupSet` `axlWindowFit` `axlZoomBbox` `axlZoomCenter` `axlZoomControl` `axlZoomFit` `axlZoomInOut` `axlZoomPoints` `axlZoomToDbid` `axlZoomWorld` 

### `09cmdshl.html` — Allegro PCB Editor Command Shell Functions

17 functions

`axlCmdRegister` `axlGetAlias` `axlGetFunckey` `axlGetVariable` `axlGetVariableList` `axlIsProtectAlias` `axlJournal` `axlProtectAlias` `axlReadOnlyVariable` `axlSetAlias` `axlSetFunckey` `axlSetVariable` `axlSetVariableFile` `axlShell` `axlShellPost` `axlUnsetVariable` `axlUnsetVariableFile` 

### `10usrint.html` — User Interface Functions

62 functions

`axlCancelClearFormClosable` `axlCancelOff` `axlCancelOn` `axlCancelSetFormClosable` `axlCancelTest` `axlClipboardGet` `axlClipboardGetText` `axlClipboardSetText` `axlCursorGet` `axlCursorWarp` `axlFormClose` `axlFormCreate` `axlIsViewFileType` `axlMeterCreate` `axlMeterDestroy` `axlMeterIsCancelled` `axlMeterUpdate` `axlUIAppMode` `axlUIColorDialog` `axlUIConfirm` `axlUIConfirmEx` `axlUIControl` `axlUIDataBrowse` `axlUIDisableQuit` `axlUIEditFile` `axlUIMenuChange` `axlUIMenuDebug` `axlUIMenuDelete` `axlUIMenuDump` `axlUIMenuFind` `axlUIMenuInsert` `axlUIMenuLoad` `axlUIMenuRegister` `axlUIMultipleChoice` `axlUIPopupDump` `axlUIPrompt` `axlUIViewFileCreate` `axlUIViewFileReuse` `axlUIViewFileScrollTo` `axlUIWBeep` `axlUIWBlock` `axlUIWClose` `axlUIWCloseAll` `axlUIWExpose` `axlUIWExposeByName` `axlUIWHelpRegister` `axlUIWIconify` `axlUIWIsIconic` `axlUIWIsWindow` `axlUIWMove` `axlUIWPerm` `axlUIWPrint` `axlUIWRedraw` `axlUIWSetHelpTag` `axlUIWSetParent` `axlUIWShow` `axlUIWSize` `axlUIWTimerAdd` `axlUIWTimerRemoveSet` `axlUIYesNo` `axlUIYesNoCancel` `axluGetString` 

### `11frmint.html` — Form Interface Functions

68 functions

`axlExtractToFile` `axlFormAutoResize` `axlFormBNFDoc` `axlFormBuildPopup` `axlFormClearMouseActive` `axlFormColorize` `axlFormDefaultButton` `axlFormDisplay` `axlFormGetActiveField` `axlFormGetField` `axlFormGetFieldType` `axlFormGetOptionValue` `axlFormGridBatch` `axlFormGridCancelPopup` `axlFormGridDeleteRows` `axlFormGridEvents` `axlFormGridGetCell` `axlFormGridGetSize` `axlFormGridInsertCol` `axlFormGridInsertRows` `axlFormGridNewCell` `axlFormGridOption` `axlFormGridOptions` `axlFormGridReset` `axlFormGridSelected` `axlFormGridSelectedCnt` `axlFormGridSetBatch` `axlFormGridSetSelectRows` `axlFormGridUpdate` `axlFormInvalidateField` `axlFormIsFieldEditable` `axlFormIsFieldVisible` `axlFormListAddItem` `axlFormListDeleteAll` `axlFormListDeleteItem` `axlFormListGetCount` `axlFormListGetItem` `axlFormListGetSelCount` `axlFormListGetSelItems` `axlFormListOptions` `axlFormListSelAll` `axlFormListSelect` `axlFormMsg` `axlFormRestoreField` `axlFormSetActiveField` `axlFormSetDecimal` `axlFormSetEventAction` `axlFormSetField` `axlFormSetFieldEditable` `axlFormSetFieldLimits` `axlFormSetFieldVisible` `axlFormSetInfo` `axlFormSetMouseActive` `axlFormTest` `axlFormTitle` `axlFormTreeViewAddItem` `axlFormTreeViewChangeImages` `axlFormTreeViewChangeLabel` `axlFormTreeViewGetImages` `axlFormTreeViewGetLabel` `axlFormTreeViewGetParents` `axlFormTreeViewGetSelectState` `axlFormTreeViewLoadBitmaps` `axlFormTreeViewSet` `axlFormTreeViewSetSelectState` `axlIsFormType` `axlIsGridCellType` `axlformSetField` 

### `12draw.html` — Simple Graphics Drawing Functions

9 functions

`axlGRPDrwBitmap` `axlGRPDrwCircle` `axlGRPDrwInit` `axlGRPDrwLine` `axlGRPDrwMapWindow` `axlGRPDrwPoly` `axlGRPDrwRectangle` `axlGRPDrwText` `axlGRPDrwUpdate` 

### `13msghnd.html` — Message Handler Functions

15 functions

`axlMsgCancelPrint` `axlMsgCancelSeen` `axlMsgClear` `axlMsgContextClear` `axlMsgContextFinish` `axlMsgContextGet` `axlMsgContextGetString` `axlMsgContextInBuf` `axlMsgContextPrint` `axlMsgContextRemove` `axlMsgContextStart` `axlMsgContextTest` `axlMsgPut` `axlMsgSet` `axlMsgTest` 

### `14dsnctl.html` — Design Control Functions

39 functions

`axlCompileSymbol` `axlCurrentDesign` `axlDBChangeDesignExtents` `axlDBChangeDesignOrigin` `axlDBChangeDesignUnits` `axlDBCheck` `axlDBCopyPadstack` `axlDBDelLock` `axlDBDellLock` `axlDBDisplayControl` `axlDBGetExtents` `axlDBGetLock` `axlDBIgnoreFixed` `axlDBIsReadOnly` `axlDBMemoryReclaim` `axlDBSectorSize` `axlDBSetLock` `axlDBTuneSectorSize` `axlDesignType` `axlExtentDB` `axlGetActiveLayer` `axlGetActiveTextBlock` `axlGetDrawingName` `axlInTrigger` `axlInTriggerFunc` `axlIsSymbolEditor` `axlKillDesign` `axlOpenDesignForBatch` `axlRenameDesign` `axlSaveDesign` `axlSaveEnable` `axlSetActiveLayer` `axlSetSymbolType` `axlTechnologyType` `axlTriggerClear` `axlTriggerPrint` `axlTriggerSet` `axlWFMAnyExported` `axloDBControl` 

### `15dbgrp.html` — Database Group Functions

15 functions

`axlDBAddGroupObjects` `axlDBCreateGroup` `axlDBDisbandGroup` `axlDBGetGroupFromItem` `axlDBGroupRename` `axlDBRemoveGroupObjects` `axlNetClassAdd` `axlNetClassCreate` `axlNetClassDelete` `axlNetClassGet` `axlNetClassRemove` `axlRegionAdd` `axlRegionCreate` `axlRegionDelete` `axlRegionRemove` 

### `16dbatt.html` — Database Attachment Functions

6 functions

`axlCreateAttachment` `axlDeleteAttachment` `axlGetAllAttachmentNames` `axlGetAttachment` `axlIsAttachment` `axlSetAttachment` 

### `17dbtran.html` — Database Transaction Functions

6 functions

`axlDBCloak` `axlDBTransactionCommit` `axlDBTransactionMark` `axlDBTransactionOops` `axlDBTransactionRollback` `axlDBTransactionStart` 

### `18consmgt.html` — Constraint Management Functions

77 functions

`axlCNSCreate` `axlCNSCsetLock` `axlCNSDFAExport` `axlCNSDFAImport` `axlCNSDFAMode` `axlCNSDelete` `axlCNSDesignGetValue` `axlCNSDesignModeGet` `axlCNSDesignModeSet` `axlCNSDesignValueCheck` `axlCNSDesignValueGet` `axlCNSDesignValueSet` `axlCNSEcseValueGet` `axlCNSEcsetCreate` `axlCNSEcsetDelete` `axlCNSEcsetGet` `axlCNSEcsetModeGet` `axlCNSEcsetModeSet` `axlCNSEcsetValueCheck` `axlCNSEcsetValueGet` `axlCNSEcsetValueSet` `axlCNSGetDefaultMinLineWidth` `axlCNSGetPhysical` `axlCNSGetPinDelayEnabled` `axlCNSGetPinDelayPVF` `axlCNSGetSameNet` `axlCNSGetSameNetXtalkEnabled` `axlCNSGetSpacing` `axlCNSGetViaZEnabled` `axlCNSGetViaZPVF` `axlCNSIsCsetLocked` `axlCNSIsLockedDomain` `axlCNSLockDomain` `axlCNSMapClear` `axlCNSMapUpdate` `axlCNSOptions` `axlCNSPhysicalModeGet` `axlCNSPhysicalModeSet` `axlCNSSameNetModeGet` `axlCNSSameNetModeSet` `axlCNSSetPhysical` `axlCNSSetPinDelayEnabled` `axlCNSSetPinDelayPVF` `axlCNSSetSameNet` `axlCNSSetSameNetXtalkEnabled` `axlCNSSetSpacing` `axlCNSSetViaZEnabledenabled` `axlCNSSetViaZPVF` `axlCNSSpacingMax` `axlCNSSpacingMin` `axlCNSSpacingModeGet` `axlCNSSpacingModeSet` `axlCnsAddVia` `axlCnsAssignPurge` `axlCnsClassTableChange` `axlCnsClassTableCreate` `axlCnsClassTableDelete` `axlCnsClassTableFind` `axlCnsClassTableSeek` `axlCnsDeleteClassClassObjects` `axlCnsDeleteRegionClassClassObjects` `axlCnsDeleteRegionClassObjects` `axlCnsDeleteVia` `axlCnsGetViaList` `axlCnsList` `axlCnsNetFlattened` `axlCnsPurgeAll` `axlCnsPurgeCsets` `axlCnsPurgeObjects` `axlDBGetWaive` `axlDRCGetCount` `axlDRCItem` `axlDRCUpdate` `axlDRCWaive` `axlDRCWaiveGetCount` `axlGetAllViaList` `axlNetEcsetValueGet` 

### `19cmdctl.html` — Command Control Functions

11 functions

`axlBuildClassPopup` `axlBuildSubclassPopup` `axlCmdUnregister` `axlEndSkillMode` `axlFlushDisplay` `axlOKToProceed` `axlSetLineLock` `axlSetRotateIncrement` `axlSubclassFormPopup` `axlUIGetUserData` `axlUIPopup` 

### `20plyopr.html` — Polygon Operation Functions

7 functions

`axlIsPolyType` `axlPolyErrorGet` `axlPolyFormDB` `axlPolyFromHole` `axlPolyMemUse` `axlPolyOffset` `axlPolyOperation` 

### `21filacc.html` — Allegro PCB Editor File Access Functions

17 functions

`axlDMBrowsePath` `axlDMClose` `axlDMDirectoryBrowse` `axlDMFileBrowse` `axlDMFileError` `axlDMFileParts` `axlDMFindFile` `axlDMGetFile` `axlDMOpenFile` `axlDMOpenLog` `axlOSFileCopy` `axlOSFileMove` `axlOSSlash` `axlRecursiveDelete` `axlTempDirectory` `axlTempFile` `axlTempFileRemove` 

### `22extrct.html` — Reports and Extract Functions

4 functions

`axlExtractMap` `axlLogHeader` `axlReportGenerate` `axlReportRegister` 

### `23utils.html` — Utility Functions

38 functions

`axlCheckString` `axlCmdList` `axlDetailLoad` `axlDetailSave` `axlEmail` `axlGetDesign` `axlHistory` `axlHttp` `axlIsDebug` `axlIsPointInsideBox` `axlIsProductLineActive` `axlIsToolbox` `axlLicDefaultVersion` `axlLicFeatureExists` `axlLicIsProductEnabled` `axlMKS2UU` `axlMKSAliaas` `axlMKSAlias` `axlMKSConvert` `axlMKSStr2UU` `axlMKSalias` `axlMemSize` `axlOSBackSlash` `axlOSControl` `axlOSExit` `axlOSNtp` `axlPPrint` `axlPdfView` `axlRegexpIs` `axlRunBatchDBProgram` `axlSort` `axlStrcmpAlpNum` `axlStringCSVParse` `axlStringRemoveSpaces` `axlVersion` `axlVersionIdGet` `axlVersionIdPrint` `axlVersionIdPrintd` 

### `24mthutl.html` — Math Utility Functions

35 functions

`axlDegToRad` `axlDistance` `axlEpsilonFloat` `axlGeo2Str` `axlGeoAngleBetweenLines` `axlGeoArcCenterAngle` `axlGeoArcCenterRadius` `axlGeoArcMidpoint` `axlGeoCircleCircleInt` `axlGeoCircleLineInt` `axlGeoCircleLineInt2` `axlGeoEqual` `axlGeoFindAngle` `axlGeoGetBBox` `axlGeoLineMidpoint` `axlGeoPickShorterArc` `axlGeoPointsEqual` `axlGeoRotatePt` `axlGeolsBoxOverlap` `axlGeolsShorterArcClockwise` `axlIsBetween` `axlIsPointOnLine` `axlLineSlope` `axlLineXLine` `axlMPythag` `axlMUniVector` `axlMXYAdd` `axlMXYMult` `axlMXYSub` `axlMathDotProduct` `axlMathSolveQuadratic` `axlMidPointArc` `axlMidPointLine` `axlRadToDeg` `axl_ol_ol2` 

### `25dbmisc.html` — Database Miscellaneous Functions

32 functions

`axlAirGap` `axlBackDrill` `axlChangeNet` `axlDBGetLength` `axlDBGetManhattan` `axlDBGetSymbolBodyExtent` `axlDBPinPairLength` `axlDeleteByLayer` `axlExtentLayout` `axlExtentSymbol` `axlFindPath` `axlGeoClosestPointOnArc` `axlGeoPointInShape` `axlGeoPointShapeInfo` `axlGetImpedance` `axlImpdedanceGetLayerBroadsideDPImp` `axlImpdedanceGetLayerBroadsideDPWidth` `axlImpdedanceGetLayerEdgeDPImp` `axlImpdedanceGetLayerEdgeDPSpacing` `axlImpdedanceGetLayerEdgeDPWidth` `axlImpedance2Width` `axlIsHighlighted` `axlPadOnLayer` `axlPinExport` `axlPinImport` `axlReratNet` `axlSegDelayAndZ0` `axlSetDefaultDieInformation` `axlTestPoint` `axlText2Lines` `axlUnfixAll` `axlWidth2Impedance` 

### `26logacc.html` — Logic Access Functions

30 functions

`axlDBAssignNet` `axlDBCreateComponent` `axlDBCreateConceptComponent` `axlDBCreateManyModuleInstances` `axlDBCreateModuleDef` `axlDBCreateModuleInstance` `axlDBCreateNet` `axlDBCreateSymDefSkeleton` `axlDBDummyNet` `axlDBNetCreate` `axlDbidName` `axlDiffPair` `axlDiffPairAuto` `axlDiffPairDBID` `axlMatchGroupAdd` `axlMatchGroupCreate` `axlMatchGroupDelete` `axlMatchGroupProp` `axlMatchGroupRemove` `axlNetSched` `axlPinPair` `axlPinPairSeek` `axlPinsOfNet` `axlRemoveNet` `axlRenameNet` `axlRenameRefdes` `axlSchedule` `axlScheduleNet` `axlWriteDeviceFile` `axlWritePackageFile` 

### `27langexten.html` — Skill Language Extensions

2 functions

`axldo` `axldoStar` 

### `27plugin.html` — Plugin Functions

6 functions

`axlDllCall` `axlDllCallList` `axlDllClose` `axlDllDump` `axlDllOpen` `axlDllSym` 

### `msexl.html` — Microsoft Excel Integration Functions

22 functions

`axlSpreadsheetClose` `axlSpreadsheetDefineCell` `axlSpreadsheetGetCell` `axlSpreadsheetGetRGBColorString` `axlSpreadsheetGetRGBForNamedColor` `axlSpreadsheetGetStyles` `axlSpreadsheetGetWorksheetSize` `axlSpreadsheetGetWorksheets` `axlSpreadsheetInit` `axlSpreadsheetRead` `axlSpreadsheetReadDelimited` `axlSpreadsheetSetCell` `axlSpreadsheetSetCellProp` `axlSpreadsheetSetColumnProp` `axlSpreadsheetSetDocProp` `axlSpreadsheetSetRowProp` `axlSpreadsheetSetStyle` `axlSpreadsheetSetStyleBorder` `axlSpreadsheetSetStyleParent` `axlSpreadsheetSetStyleProp` `axlSpreadsheetSetWorksheet` `axlSpreadsheetWrite` 

### `sipapd.html` — IC Packaging Commands

42 functions

`axlAddAutoAssignNetAlgorithm` `axlCNSAssemblyModeGet` `axlCNSAssemblyModeSet` `axlCNSGetAssembly` `axlCNSSetAssembly` `axlChangeLayer` `axlCompAddPin` `axlCompDeletePin` `axlCompMovePin` `axlCompSetPinAttributes` `axlComponentChangeClass` `axlCreateDeviceFileTemplate` `axlDBIsBondingWireLayer` `axlDBIsDiePad` `axlDBIsDieStackLayer` `axlDBIsPlatingbarPin` `axlGetAllVisibleProfiles` `axlGetDieData` `axlGetDieStackData` `axlGetDieStackMemberSet` `axlGetDieStackNames` `axlGetDieType` `axlGetIposerData` `axlGetMetalUsageForLayer` `axlGetSpacerData` `axlGetWireProfileColor` `axlGetWireProfileDefinition` `axlGetWireProfileDirection` `axlGetWireProfileVisible` `axlImportWireProfileDefinitions` `axlPackageDesignCheckAddCategory` `axlPackageDesignCheckAddCheck` `axlPackageDesignCheckDrcError` `axlPackageDesignCheckLogError` `axlSetAllProfilesVisible` `axlSetBondWireProfile` `axlSetDieData` `axlSetDieType` `axlSetIposerData` `axlSetSpacerData` `axlSetWireProfileColor` `axlSetWireProfileVisible` 

