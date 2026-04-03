# H->gammagamma Analysis Report

## Introduction

This run executes the five-category ATLAS open-data Higgs-to-diphoton measurement defined in `analysis/Higgs-to-diphoton.json` with a PyROOT/RooFit primary backend. The central measurement fit returns `mu = 0.931 +/- 0.141`, the observed discovery significance from data is `Z = 6.865` with `q0 = 47.125`, and the Asimov expected sensitivity is `Z = 7.266` with `q0 = 52.800`.

This run was explicitly unblinded, so observed and expected significance are both reported.

## Dataset Description

The run uses 16 data ROOT samples spanning the open-data periods data15_periodD, data15_periodE, data15_periodF, data15_periodG ... and 359 MC samples.

Nominal and alternative MC inputs cover generators MGH7EG, MGPy8EG, MadGraphPythia8EvtGen, PhH7EG, PhPy8EG, PowhegHerwig7EvtGen, PowhegPy8EG, PowhegPythia8EvtGen, Py8EG, Pythia8EvtGen, Sh, Sherpa, aMCH7EG, aMCPy8EG, aMcAtNloHerwig7EvtGen, aMcAtNloPy8EG, aMcAtNloPythia8EvtGen with simulation configurations 2210_eegammagamma, 2210_enugammagamma, 2210_mumugammagamma, 2210_munugammagamma, 2210_nunugammagamma, 2210_taunugammagamma, 2210_tautaugammagamma, 2211_Wenu2jets_Min_N_TChannel, 2211_Wenu_maxHTpTV2_BFilter, 2211_Wenu_maxHTpTV2_CFilterBVeto, 2211_Wenu_maxHTpTV2_CVetoBVeto, 2211_WlvWqq, 2211_WlvZbb, 2211_WlvZqq, 2211_Wmunu2jets_Min_N_TChannel, 2211_Wmunu_maxHTpTV2_BFilter, 2211_Wmunu_maxHTpTV2_CFilterBVeto, 2211_Wmunu_maxHTpTV2_CVetoBVeto, 2211_WqqZll, 2211_WqqZvv, 2211_Wtaunu2jets_Min_N_TChannel, 2211_Wtaunu_H_maxHTpTV2_BFilter, 2211_Wtaunu_H_maxHTpTV2_CFilterBVeto, 2211_Wtaunu_H_maxHTpTV2_CVetoBVeto, 2211_Wtaunu_L_maxHTpTV2_BFilter, 2211_Wtaunu_L_maxHTpTV2_CFilterBVeto, 2211_Wtaunu_L_maxHTpTV2_CVetoBVeto, 2211_ZbbZll, 2211_ZbbZvv, 2211_Zee2jets_Min_N_TChannel, 2211_Zee_maxHTpTV2_BFilter, 2211_Zee_maxHTpTV2_CFilterBVeto, 2211_Zee_maxHTpTV2_CVetoBVeto, 2211_Zee_maxHTpTV2_m10_40_pT5_BFilter, 2211_Zee_maxHTpTV2_m10_40_pT5_CFilterBVeto, 2211_Zee_maxHTpTV2_m10_40_pT5_CVetoBVeto, 2211_Zmm2jets_Min_N_TChannel, 2211_Zmumu_maxHTpTV2_BFilter, 2211_Zmumu_maxHTpTV2_CFilterBVeto, 2211_Zmumu_maxHTpTV2_CVetoBVeto, 2211_Zmumu_maxHTpTV2_m10_40_pT5_BFilter, 2211_Zmumu_maxHTpTV2_m10_40_pT5_CFilterBVeto, 2211_Zmumu_maxHTpTV2_m10_40_pT5_CVetoBVeto, 2211_Znunu2jets_Min_N_TChannel, 2211_Znunu_pTV2_BFilter, 2211_Znunu_pTV2_CFilterBVeto, 2211_Znunu_pTV2_CVetoBVeto, 2211_ZqqZll, 2211_ZqqZvv, 2211_Ztt2jets_Min_N_TChannel, 2211_eegamma, 2211_enugamma, 2211_gamma2jets_pTy140_Min_N_TChannel, 2211_mumugamma, 2211_munugamma, 2211_nunugamma, 2211_pTW140_Wqqgamma, 2211_pTZ100_Zbbgamma, 2211_pTZ100_Zqqgamma, 2211_taunugamma, 2211_tautaugamma, 2212_llll, 2212_lllljj, 2212_lllljj_Int, 2212_lllvjj, 2212_lllvjj_Int, 2212_llvv_ss, 2212_llvvjj_os, 2212_llvvjj_ss, 2212_lvgammajj, 2214_Zbb_ptZ_200_ECMS, 2214_Zqq_ptZ_200_ECMS, 2214_Ztautau_maxHTpTV2_CVetoBVeto, 222_NNPDF30NNLO_SinglePhoton_pty_1000_E_CMS, 222_NNPDF30NNLO_SinglePhoton_pty_140_280, 222_NNPDF30NNLO_SinglePhoton_pty_17_35, 222_NNPDF30NNLO_SinglePhoton_pty_280_500, 222_NNPDF30NNLO_SinglePhoton_pty_35_70, 222_NNPDF30NNLO_SinglePhoton_pty_500_1000, 222_NNPDF30NNLO_SinglePhoton_pty_70_140, 222_NNPDF30NNLO_WWW_3l3v_EW6, 222_NNPDF30NNLO_WWZ_2l4v_EW6, 222_NNPDF30NNLO_WWZ_4l2v_EW6, 222_NNPDF30NNLO_WZZ_3l3v_EW6, 222_NNPDF30NNLO_WZZ_5l1v_EW6, 222_NNPDF30NNLO_WnWnWp_oslvlvjj_EW6, 222_NNPDF30NNLO_WnWnWp_sslvlvjj_EW6, 222_NNPDF30NNLO_WpWpWn_oslvlvjj_EW6, 222_NNPDF30NNLO_WpWpWn_sslvlvjj_EW6, 222_NNPDF30NNLO_ZZZ_2l4v_EW6, 222_NNPDF30NNLO_ZZZ_4l2v_EW6, 222_NNPDF30NNLO_ZZZ_6l0v_EW6, 224_NNPDF30NNLO_Diphoton_myy_0_50, 224_NNPDF30NNLO_Diphoton_myy_175_2000, 224_NNPDF30NNLO_Diphoton_myy_2000_E_CMS, 224_NNPDF30NNLO_Diphoton_myy_50_90, 224_NNPDF30NNLO_Diphoton_myy_90_175, 228_ttW, 228_yyy_01NLO, A14MSTW2008LO_Zprime_NoInt_ee_SSM3000, A14MSTW2008LO_Zprime_NoInt_mumu_SSM3000, A14N23LO_C1N2N1_GGMHinoZh50_800_noFilter, A14N23LO_C1N2_WZ_500p0_100p0_3L_2L7, A14N23LO_DMA_500_700_gq0p25, A14N23LO_DM_4topscalar_p1000_c1_nonallhad, A14N23LO_SM_N2C1p_105_100_2L2MET75_MadSpin, A14N23LO_SS_onestepCC_1600_900_200, A14N23LO_TT_RPVdirectBL_1400, A14N23LO_TT_higgsinoRPV_1075_700, A14N23LO_TT_tN1_1200_200_MS, A14N30NLO_LQd_gstML_0p3_nonallhad_M1000, A14NNPDF23LO_2DP20_Mass_1000_1500, A14NNPDF23LO_2DP20_Mass_100_160, A14NNPDF23LO_2DP20_Mass_1500_2000, A14NNPDF23LO_2DP20_Mass_160_250, A14NNPDF23LO_2DP20_Mass_2000_2500, A14NNPDF23LO_2DP20_Mass_2500_3000, A14NNPDF23LO_2DP20_Mass_250_400, A14NNPDF23LO_2DP20_Mass_3000_3500, A14NNPDF23LO_2DP20_Mass_3500_4000, A14NNPDF23LO_2DP20_Mass_4000_4500, A14NNPDF23LO_2DP20_Mass_400_650, A14NNPDF23LO_2DP20_Mass_4500_5000, A14NNPDF23LO_2DP20_Mass_5000_inf, A14NNPDF23LO_2DP20_Mass_55_100, A14NNPDF23LO_2DP20_Mass_650_1000, A14NNPDF23LO_GGM_N1N2C1_950, A14NNPDF23LO_GG_direct_2400_200, A14NNPDF23LO_WpL_tbhad_M3000, A14NNPDF23LO_WpL_tblep_M3000, A14NNPDF23LO_Wprime_enu_SSM3000, A14NNPDF23LO_Wprime_munu_SSM3000, A14NNPDF23LO_Wprime_qq_3000, A14NNPDF23LO_Zprime_NoInt_tautau_SSM3000, A14NNPDF23LO_Zprimebb3000, A14NNPDF23LO_gammajet_DP1000_1500, A14NNPDF23LO_gammajet_DP140_280, A14NNPDF23LO_gammajet_DP1500_2000, A14NNPDF23LO_gammajet_DP17_35, A14NNPDF23LO_gammajet_DP2000_2500, A14NNPDF23LO_gammajet_DP2500_3000, A14NNPDF23LO_gammajet_DP280_500, A14NNPDF23LO_gammajet_DP3000_inf, A14NNPDF23LO_gammajet_DP35_50, A14NNPDF23LO_gammajet_DP500_800, A14NNPDF23LO_gammajet_DP50_70, A14NNPDF23LO_gammajet_DP70_140, A14NNPDF23LO_gammajet_DP800_1000, A14NNPDF23LO_gammajet_DP8_17, A14NNPDF23LO_jetjet_JZ0WithSW, A14NNPDF23LO_jetjet_JZ10WithSW, A14NNPDF23LO_jetjet_JZ11WithSW, A14NNPDF23LO_jetjet_JZ12WithSW, A14NNPDF23LO_jetjet_JZ1WithSW, A14NNPDF23LO_jetjet_JZ2WithSW, A14NNPDF23LO_jetjet_JZ3WithSW, A14NNPDF23LO_jetjet_JZ4WithSW, A14NNPDF23LO_jetjet_JZ5WithSW, A14NNPDF23LO_jetjet_JZ6WithSW, A14NNPDF23LO_jetjet_JZ7WithSW, A14NNPDF23LO_jetjet_JZ8WithSW, A14NNPDF23LO_jetjet_JZ9WithSW, A14NNPDF23LO_ppx0_FxFx_Np012_SM, A14NNPDF23LO_ppx0yy_FxFx_Np012_SM, A14NNPDF23LO_ttgamma_allhad, A14NNPDF23LO_ttgamma_noallhad, A14NNPDF23LO_zprime3000_tt, A14NNPDF23_3top_SM, A14NNPDF23_NNPDF30ME_ttH125_ZZ4l_allhad, A14NNPDF23_NNPDF30ME_ttH125_ZZ4l_dilep, A14NNPDF23_NNPDF30ME_ttH125_ZZ4l_semilep, A14NNPDF23_NNPDF30ME_ttH125_ZZ4nu_allhad, A14NNPDF23_NNPDF30ME_ttH125_ZZ4nu_dilep, A14NNPDF23_NNPDF30ME_ttH125_ZZ4nu_semilep, A14NNPDF23_NNPDF30ME_ttH125_Zgam, A14NNPDF23_NNPDF30ME_ttH125_allhad, A14NNPDF23_NNPDF30ME_ttH125_allhad_tautau_unpol, A14NNPDF23_NNPDF30ME_ttH125_dilep, A14NNPDF23_NNPDF30ME_ttH125_dilep_tautau_unpol, A14NNPDF23_NNPDF30ME_ttH125_gamgam, A14NNPDF23_NNPDF30ME_ttH125_semilep, A14NNPDF23_NNPDF30ME_ttH125_semilep_tautau_unpol, A14NNPDF23_ttbarWW, A14NNPDF23_ttgamma_nonallhadronic, A14NNPDF31_SM4topsNLO, A14N_GG_ttn1_2000_5000_200, A14_singletop_schan_lept_antitop, A14_singletop_schan_lept_top, A14_tZ_4fl_tchan_noAllHad, A14_tchan_BW50_lept_antitop, A14_tchan_BW50_lept_top, A14_tchan_pThard1_lep_antitop, A14_tchan_pThard1_lep_top, A14_ttbar_hdamp258p75_allhad, A14_ttbar_hdamp258p75_nonallhad, A14_ttbar_pThard1_allhad, A14_ttbar_pThard1_dil, A14_ttbar_pThard1_singlelep, AZNLOCTEQ6L1_ggfhtautauhhNp2, AZNLOCTEQ6L1_ggfhtautaulhNp2, AZNLOCTEQ6L1_ggfhtautaullNp2, CT10_AZNLO_ZH125J_MINLO_veveWWlvqq_VpT, CT10_AZNLO_ZH125J_MINLO_vmuvmuWWlvqq_VpT, CT10_AZNLO_ZH125J_MINLO_vtauvtauWWlvqq_VpT, H7UE_716_schan_lept_antitop, H7UE_716_schan_lept_top, H7UE_716_tchan_lept_antitop, H7UE_716_tchan_lept_top, H7UE_NNLOPS_nnlo_30_ggH125_ZZ4l_noTau, H7UE_NNLOPS_nnlo_30_ggH125_gamgam, H7UE_NNPDF30ME_ttH125_ZZ4l_allhad_noTau, H7UE_NNPDF30ME_ttH125_ZZ4l_dilep_noTau, H7UE_NNPDF30ME_ttH125_ZZ4l_semilep_noTau, H7UE_NNPDF30ME_ttH125_gamgam, H7UE_NNPDF30_VBF125_gammagamma, H7UE_NNPDF30_VBFH125_ZZ4lep_noTau, H7UE_NNPDF30_WmH125J_Wincl_MINLO, H7UE_NNPDF30_WmH125J_Wincl_MINLO_gammagamma, H7UE_NNPDF30_WpH125J_Wincl_MINLO, H7UE_NNPDF30_WpH125J_Wincl_MINLO_gammagamma, H7UE_NNPDF30_ZH125J_Zincl_MINLO, H7UE_NNPDF30_ZH125J_Zincl_MINLO_gammagamma, H7UE_NNPDF30_ggZH125_gammagamma, H7UE_NNPDF3_ggZH125_ZZ4lepZinc, H7UE_SM4topsNLO, H7UE_ttgamma_allhadronic, H7UE_ttgamma_nonallhadronic, MEN30NLO_A14N23LO_ttW, MEN30NLO_A14N23LO_ttZnunu, MEN30NLO_A14N23LO_ttZqq, MEN30NLO_A14N23LO_ttee, MEN30NLO_A14N23LO_ttmumu, MEN30NLO_A14N23LO_tttautau, MEN30NLO_tHjb125_gamgam, MEN30NLO_ttH125_gamgam, NNLOPS_NN30_ggH125_WWlvlv_EF_15_5, NNLOPS_nnlo_30_VBFH125_ZZllbb, NNLOPS_nnlo_30_ggH125_WWlvlv_noTau, NNLOPS_nnlo_30_ggH125_ZZ4l, NNLOPS_nnlo_30_ggH125_ZZ4nu_MET75, NNLOPS_nnlo_30_ggH125_Zy_Zll, NNLOPS_nnlo_30_ggH125_etau_filt, NNLOPS_nnlo_30_ggH125_gamgam, NNLOPS_nnlo_30_ggH125_gamstargam, NNLOPS_nnlo_30_ggH125_mumu, NNLOPS_nnlo_30_ggH125_mutau_filt, NNLOPS_nnlo_30_ggH125_tautauh30h20, NNLOPS_nnlo_30_ggH125_tautaul13l7, NNLOPS_nnlo_30_ggH125_tautaulm15hp20, NNLOPS_nnlo_30_ggH125_tautaulp15hm20, NNPDF30_AZNLOCTEQ6L1_VBFH125_WWlvlv, NNPDF30_AZNLOCTEQ6L1_VBFH125_ZZ4lep_notau, NNPDF30_AZNLOCTEQ6L1_VBFH125_Zllgam, NNPDF30_AZNLOCTEQ6L1_VBFH125_bb, NNPDF30_AZNLOCTEQ6L1_VBFH125_etau_filt, NNPDF30_AZNLOCTEQ6L1_VBFH125_gamgam, NNPDF30_AZNLOCTEQ6L1_VBFH125_gamstargam, NNPDF30_AZNLOCTEQ6L1_VBFH125_incl, NNPDF30_AZNLOCTEQ6L1_VBFH125_mumu, NNPDF30_AZNLOCTEQ6L1_VBFH125_mutau_filt, NNPDF30_AZNLOCTEQ6L1_VBFH125_tautauh30h20, NNPDF30_AZNLOCTEQ6L1_VBFH125_tautaul13l7, NNPDF30_AZNLOCTEQ6L1_VBFH125_tautaulm15hp20, NNPDF30_AZNLOCTEQ6L1_VBFH125_tautaulp15hm20, NNPDF30_AZNLO_WmH125J_HZy_Wincl_MINLO, NNPDF30_AZNLO_WmH125J_Hee_Wincl_MINLO, NNPDF30_AZNLO_WmH125J_Hgamstargam_MINLO, NNPDF30_AZNLO_WmH125J_Hmumu_Wincl_MINLO, NNPDF30_AZNLO_WmH125J_Hyy_Wincl_MINLO, NNPDF30_AZNLO_WmH125J_Winc_MINLO_etau, NNPDF30_AZNLO_WmH125J_Winc_MINLO_mutau, NNPDF30_AZNLO_WmH125J_Winc_MINLO_tautau, NNPDF30_AZNLO_WmH125J_WinclHinv_MET75, NNPDF30_AZNLO_WmH125J_Wincl_H_incl_MINLO, NNPDF30_AZNLO_WmH125J_Wincl_MINLO_shw, NNPDF30_AZNLO_WpH125J_HZy_Wincl_MINLO, NNPDF30_AZNLO_WpH125J_Hee_Wincl_MINLO, NNPDF30_AZNLO_WpH125J_Hgamstargam_MINLO, NNPDF30_AZNLO_WpH125J_Hmumu_Wincl_MINLO, NNPDF30_AZNLO_WpH125J_Hyy_Wincl_MINLO, NNPDF30_AZNLO_WpH125J_Winc_MINLO_etau, NNPDF30_AZNLO_WpH125J_Winc_MINLO_mutau, NNPDF30_AZNLO_WpH125J_Winc_MINLO_tautau, NNPDF30_AZNLO_WpH125J_WinclHinv_MET75, NNPDF30_AZNLO_WpH125J_Wincl_H_incl_MINLO, NNPDF30_AZNLO_WpH125J_Wincl_MINLO_shw, NNPDF30_AZNLO_ZH125J_HZy_Zincl_MINLO, NNPDF30_AZNLO_ZH125J_Hee__Zincl_MINLO, NNPDF30_AZNLO_ZH125J_Hgamstargam_MINLO, NNPDF30_AZNLO_ZH125J_Hmumu_Zincl_MINLO, NNPDF30_AZNLO_ZH125J_Hyy_Zincl_MINLO, NNPDF30_AZNLO_ZH125J_Zinc_MINLO_etau, NNPDF30_AZNLO_ZH125J_Zinc_MINLO_mutau, NNPDF30_AZNLO_ZH125J_Zinc_MINLO_tautau, NNPDF30_AZNLO_ZH125J_ZinclHinv_MET75, NNPDF30_AZNLO_ZH125J_Zincl_H_incl_MINLO, NNPDF30_AZNLO_ZH125J_Zincl_MINLO_shw, NNPDF30_VBFH125_WWlvlv, NNPDF3_AZNLO_WmH125J_MINLO_qqWWlvlv, NNPDF3_AZNLO_WpH125J_MINLO_qqWWlvlv, NNPDF3_AZNLO_ZH125J_MINLO_vvWWlvlv, NNPDF3_AZNLO_ZH125J_MINLO_vvbb_VpT, NNPDF3_AZNLO_ZH125J_MINLO_vvcc_VpT, NNPDF3_AZNLO_ggZH125J_MINLO_ZinclWWlvlv, NNPDF3_AZNLO_ggZH125J_vvbb, NNPDF3_AZNLO_ggZH125J_vvcc, NNPDF3_AZNLO_ggZH125_HgamgamZinc, NNPDF3_AZNLO_ggZH125_Hmumu_Zinc, NNPDF3_AZNLO_ggZH125_Htautau_Zinc, NNPDF3_AZNLO_ggZH125_ZZ4lepZinc, NNPDF3_AZNLO_ggZH125_Zinc_HZZinv, NNPDF3_AZNLO_ggZH125_vvbb, NNPDF3_AZNLO_ggZH125_vvcc, StauStauDirect_200p0_1p0_TFilt, VBFH125_tautauh30h20_ShowerSys_fix, VBFH125_tautaul13l7_ShowerSys_fix, VBFH125_tautaulm15hp20_ShowerSys_fix, VBFH125_tautaulp15hm20_ShowerSys_fix, VBFHWWlvlv, VBF_HC_Hyy, VBF_Htautauh30h20, VBF_Htautaul13l7, VBF_Htautaulm15hp20, VBF_Htautaulp15hm20, WH_FxFx_Hyy, WmH125J_Winc_MINLO_tt_ShowerSys_fix, WpH125J_Winc_MINLO_tt_ShowerSys_fix, WpH_FxFx_Htautau, ZH125J_Zinc_MINLO_tautau_ShowerSys_fix, ZH_FxFx_Htautau, ZH_FxFx_Hyy, ZH_had_FxFx_Hyy, ggH125_tautauh30h20_ShowerSys_fix, ggH125_tautaul13l7_ShowerSys_fix, ggH125_ttlm15hp20_ShowerSys_fix, ggH125_ttlp15hm20_ShowerSys_fix, ggZH_Hyy, ggZH_Zhad_Hyy, tHjb125_4fl_ZZ4l, tHjb125_4fl_gamgam, tWH125_ZZ4l, tWH125_yy, tWZ_Ztoll_minDR1, tW_DS_dyn_dil_antitop, tW_DS_dyn_dil_top, tW_DS_dyn_incl_antitop, tW_DS_dyn_incl_top, tW_dyn_DR_incl_antitop, tW_dyn_DR_incl_top, tW_dyn_DR_pThard1_dil_antitop, tW_dyn_DR_pThard1_dil_top, tW_dyn_DR_pThard1_incl_antitop, tW_dyn_DR_pThard1_incl_top, ttH_gamgam, tt_hdamp258p75_713_SingleLep, tt_hdamp258p75_713_allhad, tt_hdamp258p75_713_dil.

- Experiment: ATLAS
- Analysis name: H_to_gammagamma_open_data_5cat
- Center-of-mass energy: 13 TeV
- Target luminosity: 36.1 fb-1
- Primary backend: `pyroot_roofit`

## Object Definitions And Event Selection

- Photons must satisfy `pT > 25 GeV`, `|eta| < 2.37`, crack veto `1.37 < |eta| < 1.52`, and tight ID/isolation.
- The diphoton selection requires `pT_lead / m_gg >= 0.35` and `pT_sublead / m_gg >= 0.25`.
- Jets are reconstructed with `pT > 25 GeV` and `|eta| < 4.5`.
- The fit range is `105-160 GeV` with plots shown across the full signal region, including `120-130 GeV`.

## Signal, Control, And Blinding Regions

- Signal regions: SR_2JET, SR_CENTRAL_LOW_PTT, SR_CENTRAL_HIGH_PTT, SR_REST_LOW_PTT, SR_REST_HIGH_PTT
- Control region: CR_BKG_VALIDATION with sideband validation in `105-120 GeV` and `130-160 GeV`
- Active fit categories in this run: central_high_ptt, central_low_ptt, rest_high_ptt, rest_low_ptt, two_jet_vbf_enriched
- Inactive configured regions: none
- Blinding policy: observed data are shown across the full fit range and observed significance is enabled for this explicitly unblinded run

## Nominal Samples And Background Strategy

The nominal signal samples were chosen by process-key matching and generator preference. The nominal prompt-diphoton sample used for the spurious-signal workflow is `364352`, corresponding to the minimum generated-mass window that fully contains `105-160 GeV`.

The prompt-diphoton template is normalized to observed data in the sidebands `105-120 GeV` and `130-160 GeV`. This keeps the nominal spurious-signal template anchored to diphoton MC while acknowledging that the observed continuum background also contains `gamma+jet`, `jet+jet`, and `Z->ee` fake-photon contributions.

The effective prompt-diphoton MC luminosity recorded in `outputs/report/mc_effective_lumi_check.json` is `59.507 fb^-1`, compared with the required threshold `361.0 fb^-1`. The smoothing gate status is `ok` with observed method `TH1::Smooth`.

## Distribution Plots

![Preselection diphoton mass](../outputs_unblinded_full_fixed_20260403/report/plots/events/diphoton_mass_preselection.png)

*Caption:* Unblinded preselection diphoton-mass spectrum. Data points are shown across the full 105-160 GeV fit range, including the former signal window.
![Cut flow](../outputs_unblinded_full_fixed_20260403/report/plots/events/cutflow_plot.png)

*Caption:* Cut-flow comparison for data, prompt-diphoton MC, and nominal signal MC. This figure documents how the event selection contracts the sample before the category assignment.
![Prefit sidebands central_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/control_regions/prefit_sidebands_central_high_ptt.png)

*Caption:* Pre-fit category validation for central high ptt. Data are shown across the full fit range and compared with the prompt-diphoton template plus signal overlay.
![Postfit mass central_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/fits/diphoton_mass_fit_central_high_ptt.png)

*Caption:* Post-fit category mass spectrum for central high ptt. The full observed spectrum is compared with the fitted analytic background plus signal expectation.
![Signal shape central_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/signal_shape/signal_mgg_central_high_ptt.png)

*Caption:* Signal-shape validation for central high ptt. The weighted signal MC distribution is overlaid with the fitted double-sided Crystal Ball PDF used downstream in the combined likelihood.
![Prefit sidebands central_low_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/control_regions/prefit_sidebands_central_low_ptt.png)

*Caption:* Pre-fit category validation for central low ptt. Data are shown across the full fit range and compared with the prompt-diphoton template plus signal overlay.
![Postfit mass central_low_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/fits/diphoton_mass_fit_central_low_ptt.png)

*Caption:* Post-fit category mass spectrum for central low ptt. The full observed spectrum is compared with the fitted analytic background plus signal expectation.
![Signal shape central_low_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/signal_shape/signal_mgg_central_low_ptt.png)

*Caption:* Signal-shape validation for central low ptt. The weighted signal MC distribution is overlaid with the fitted double-sided Crystal Ball PDF used downstream in the combined likelihood.
![Prefit sidebands rest_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/control_regions/prefit_sidebands_rest_high_ptt.png)

*Caption:* Pre-fit category validation for rest high ptt. Data are shown across the full fit range and compared with the prompt-diphoton template plus signal overlay.
![Postfit mass rest_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/fits/diphoton_mass_fit_rest_high_ptt.png)

*Caption:* Post-fit category mass spectrum for rest high ptt. The full observed spectrum is compared with the fitted analytic background plus signal expectation.
![Signal shape rest_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/signal_shape/signal_mgg_rest_high_ptt.png)

*Caption:* Signal-shape validation for rest high ptt. The weighted signal MC distribution is overlaid with the fitted double-sided Crystal Ball PDF used downstream in the combined likelihood.
![Prefit sidebands rest_low_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/control_regions/prefit_sidebands_rest_low_ptt.png)

*Caption:* Pre-fit category validation for rest low ptt. Data are shown across the full fit range and compared with the prompt-diphoton template plus signal overlay.
![Postfit mass rest_low_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/fits/diphoton_mass_fit_rest_low_ptt.png)

*Caption:* Post-fit category mass spectrum for rest low ptt. The full observed spectrum is compared with the fitted analytic background plus signal expectation.
![Signal shape rest_low_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/signal_shape/signal_mgg_rest_low_ptt.png)

*Caption:* Signal-shape validation for rest low ptt. The weighted signal MC distribution is overlaid with the fitted double-sided Crystal Ball PDF used downstream in the combined likelihood.
![Prefit sidebands two_jet_vbf_enriched](../outputs_unblinded_full_fixed_20260403/report/plots/control_regions/prefit_sidebands_two_jet_vbf_enriched.png)

*Caption:* Pre-fit category validation for two jet vbf enriched. Data are shown across the full fit range and compared with the prompt-diphoton template plus signal overlay.
![Postfit mass two_jet_vbf_enriched](../outputs_unblinded_full_fixed_20260403/report/plots/fits/diphoton_mass_fit_two_jet_vbf_enriched.png)

*Caption:* Post-fit category mass spectrum for two jet vbf enriched. The full observed spectrum is compared with the fitted analytic background plus signal expectation.
![Signal shape two_jet_vbf_enriched](../outputs_unblinded_full_fixed_20260403/report/plots/signal_shape/signal_mgg_two_jet_vbf_enriched.png)

*Caption:* Signal-shape validation for two jet vbf enriched. The weighted signal MC distribution is overlaid with the fitted double-sided Crystal Ball PDF used downstream in the combined likelihood.
![Unsmoothed template central_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/smoothing_sb_fit/unsmoothed_template_central_high_ptt.png)

*Caption:* Nominal unsmoothed sideband-normalized prompt-diphoton template for central high ptt. This plot documents the provenance template before any smoothing-based function-selection step.
![Selected spurious fit central_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/smoothing_sb_fit/selected_spurious_fit_central_high_ptt.png)

*Caption:* Selected background-function-plus-signal fit used for the spurious-signal study in central high ptt. This figure makes the fitted template choice auditable.
![Smoothing overlay central_high_ptt](../outputs_unblinded_full_fixed_20260403/report/plots/smoothing_sb_fit/smoothing_effect_overlay_central_high_ptt.png)

*Caption:* Unsmoothed-versus-smoothed prompt-diphoton template overlay for central high ptt. The ratio panel shows the direct effect of the mandatory TH1-based smoothing step.
![Asimov free-mu fit combined](../outputs_unblinded_full_fixed_20260403/report/plots/asimov_fits/diphoton_mass_asimov_free_fit.png)

*Caption:* Combined Asimov signal-plus-background pseudo-data fit with free signal strength. This diagnostic shows the model used in the unconditional significance fit over the full 105-160 GeV range.
![Asimov mu0 fit combined](../outputs_unblinded_full_fixed_20260403/report/plots/asimov_fits/diphoton_mass_asimov_mu0_fit.png)

*Caption:* Combined Asimov signal-plus-background pseudo-data fit with mu fixed to zero. This plot visualizes the background-only hypothesis used in the conditional significance test.

## Cut Flow And Category Yields

| Step | Data entries | Prompt diphoton yield | Signal yield |
| --- | --- | --- | --- |
| all_events | 36564144 | 839122.51 | 2156.52 |
| two_photons | 1660629 | 419349.61 | 1369.71 |
| pt_fraction | 1448552 | 345883.14 | 1249.37 |
| mass_window | 228498 | 189371.34 | 1248.41 |
| categorized | 228498 | 189371.34 | 1248.41 |

| Category | Data entries | Prompt diphoton yield | Signal yield |
| --- | --- | --- | --- |
| two_jet_vbf_enriched | 510 | 475.12 | 7.19 |
| central_low_ptt | 33327 | 29850.29 | 235.86 |
| central_high_ptt | 2587 | 2703.18 | 66.96 |
| rest_low_ptt | 176815 | 142183.24 | 747.48 |
| rest_high_ptt | 15259 | 14159.51 | 190.92 |

## Statistical Interpretation

- Fit status: `warning` (`fit_status=1`, `cov_qual=2`)
- Fit dataset: `observed` (observed selected events over the full 105-160 GeV range)
- Shared POI across categories: `True`
- Best-fit `mu`: `0.931 +/- 0.141`
- Observed significance: `Z = 6.865`
- Observed `q0`: `47.125`
- Asimov expected significance: `Z = 7.266`
- Asimov `q0`: `52.800`
- Asimov generation hypothesis: `mu_gen = 1.0` with dataset type `asimov`
- Fit diagnostics: RooFit returned non-zero fit_status for the combined measurement fit., Minuit2 migrad returned a non-zero status for the combined measurement fit., Minuit2 hesse returned a non-zero status for the combined measurement fit., Spurious-signal model selection reached the complexity-3 cap without satisfying the target in categories: central_high_ptt, central_low_ptt, rest_high_ptt, rest_low_ptt, two_jet_vbf_enriched.
- Observed significance diagnostics: Free-mu observed significance fit returned a non-zero RooFit status., Mu=0 observed significance fit returned a non-zero RooFit status., Free-mu observed significance migrad returned a non-zero Minuit2 status., Mu=0 observed significance migrad returned a non-zero Minuit2 status., Free-mu observed significance hesse returned a non-zero Minuit2 status., Mu=0 observed significance hesse returned a non-zero Minuit2 status.
- Significance diagnostics: Free-mu Asimov significance fit returned a non-zero RooFit status., Mu=0 Asimov significance fit returned a non-zero RooFit status., Free-mu Asimov significance migrad returned a non-zero Minuit2 status., Mu=0 Asimov significance migrad returned a non-zero Minuit2 status., Free-mu Asimov significance hesse returned a non-zero Minuit2 status., Mu=0 Asimov significance hesse returned a non-zero Minuit2 status.

## Governance And Validation

- Data-MC discrepancy status: `no_substantial_discrepancy`
- Skill extraction status: `none_found`
- Skill checkpoint status: `pass`
- Plot groups produced: asimov_fits, categories, control_regions_postfit, control_regions_prefit, events, fits, objects, signal_shape, smoothing_sb_fit
- Capped spurious-signal outcome categories: two_jet_vbf_enriched, central_low_ptt, central_high_ptt, rest_low_ptt, rest_high_ptt

## Appendix: Nominal Sample Selection Rationale

- Selected nominal prompt-diphoton sample: `364352`
- Alternative prompt-diphoton samples excluded from the nominal template: 364350, 364351, 364353, 364354
- Signal/background role assignment follows `outputs/report/mc_sample_selection.json` and excludes low-statistics auxiliary backgrounds from the nominal spurious-signal template.

## Summary

The pipeline completed bootstrap, selection, histogramming, RooFit modeling, expected-significance evaluation, plotting, discrepancy auditing, and report generation for the Higgs-to-diphoton workflow. Final handoff readiness remains governed by the machine-readable review and enforcement artifacts written alongside this report.
