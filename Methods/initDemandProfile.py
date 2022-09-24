# -*- coding: utf-8 -*-
"""
Created on 06/03/2022
@author:Jorge 


Extract from opendss the native load and multiply it by a load shape
"""
import numpy as np
import pathlib
import pandas as pd
from Methods.loadHelper import loadHelper


def get_1ph_demand(dss, mv_node_name):
    "Method to extract the demand from a feeder"
    # create a dictionary from node names
    load_power_dict = {key: 0 for key in mv_node_name}
    load_Q_dict = {key: 0 for key in mv_node_name}
    loadNameDict = dict()
    elems = dss.circuit_all_element_names()
    for i, elem in enumerate(elems):
        dss.circuit_set_active_element(elem)
        if "Load" in elem:
            
            # extract load name
            loadName = elem.split(".")[1]
            
            # write load name
            dss.loads_write_name(loadName)
            
            # get bus name  
            buses = dss.cktelement_read_bus_names()
            bus = buses[0]
            
            # save name
            loadNameDict[bus] = loadName
            
            # save kw
            load_power_dict[bus] = dss.loads_read_kw()
            load_Q_dict[bus] = dss.loads_read_kvar()
            
    return pd.Series(loadNameDict), pd.Series(load_power_dict), pd.Series(load_Q_dict)


def load_hourlyDemand(scriptPath, numLoads, freq):
    hourlyDemand_file = pathlib.Path(scriptPath).joinpath("inputs", "HourlyDemands100.xlsx")
    # extract demand for august 14 - 2018.
    t = pd.read_excel(hourlyDemand_file, sheet_name='august14')
    t = t.set_index('Hour')
    # create load helper method
    help_obj = loadHelper(initfreq='H', finalFreq=freq)
    # call method for processing series
    dfDemand = help_obj.process_pdFrame(t)
    return dfDemand


def load_GenerationMix(script_path, freq):
    GenMix_file = pathlib.Path(script_path).joinpath("inputs", "GeorgiaGenerationMix2.xlsx")
    t = pd.read_excel(GenMix_file)
    # create load helper method
    help_obj = loadHelper(initfreq='H', finalFreq=freq)
    # load genalpha with interpolation
    genAlpha = t["Alpha"]
    # call method for processing series
    genAlpha = help_obj.process_pdSeries(genAlpha)
    # load genbeta with interpolation
    genBeta = t["Beta"]  # load shape for 2018-08-14
    # call method for processing series
    genBeta = help_obj.process_pdSeries(genBeta)
    return genAlpha, genBeta


def getInitDemand(dss, initParams):

    # preprocesss
    script_path = initParams["script_path"]
    freq = initParams["freq"]
    loadMult = int(initParams["loadMult"])
    userDemand = initParams["userDemand"]

    # get all node-based buses
    nodeNames = dss.circuit_all_node_names()

    # get native load
    loadNames, loadKws, loadKvars = get_1ph_demand(dss, nodeNames)

    # expand dims of native load
    demandProfile = loadKws.to_frame()
    demandQrofile = loadKvars.to_frame()
    
    dfDemand = pd.DataFrame(demandProfile)
    dfDemand.index = loadKws.index

    dfDemandQ = pd.DataFrame(demandQrofile)
    dfDemandQ.index = loadKvars.index

    if freq != 'day':
        
        # get native loadshape
        _, genBeta = load_GenerationMix(script_path, freq)

        # Expand feeder demand for time series analysis
        demandProfile = demandProfile.values @ genBeta.values.T  # 2018-08-14
        demandQrofile = demandQrofile.values @ genBeta.values.T  # 2018-08-14

        # Active Power df
        dfDemand = pd.DataFrame(demandProfile)
        dfDemand.index = loadKws.index
        dfDemand.columns = genBeta.index.strftime('%H:%M')
        
        if loadMult < 5:  # DSS default load shape
            dfDemandQ = pd.DataFrame(demandQrofile)
            dfDemandQ.index = loadKvars.index
            dfDemandQ.columns = genBeta.index.strftime('%H:%M')
            # expand dims of native load
            demandProfile *= loadMult
            demandQrofile *= loadMult

        elif loadMult >= 5:  # real demand load shape
            # get real active power load
            #############
            realDemand = load_hourlyDemand(script_path, len(loadNames), freq)
            realDemand = realDemand.T
            realDemand = realDemand[:len(loadNames)]
            realDemand = loadMult * realDemand
            dfDemand.loc[loadNames.index, :] = realDemand.values
            # Reactive Power df
            np.random.seed(2022)
            PF = 0.9 #np.random.uniform(0.85, 1, size=len(dfDemand.index))
            dfDemandQ = (np.tan(np.arccos(PF)) * dfDemand.T).T

        # correct native load by user demand
        if userDemand != "None":
            dfDemand.loc[loadNames.index, :] = userDemand

    # initialize out DSS dict with init demand values
    initDSS = dict()
    initDSS["loadNames"] = loadNames
    initDSS["dfDemand"] = dfDemand
    initDSS["dfDemandQ"] = dfDemandQ

    return initDSS