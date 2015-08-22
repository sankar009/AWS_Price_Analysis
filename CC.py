from urllib import urlopen
from flask import Flask, jsonify
from json import loads, dumps

app = Flask(__name__)

@app.route('/vcpu/price')
def vcpu():
	onDemand, Spot = LoadInstances()
	vCPUList = vCPUInfo(onDemand, Spot)
	topTen = vCPUList[0:10]
	return jsonify({'cheapestvCPUInstances': topTen})

@app.route('/regions/cheapest')
def CheapestRegion():
	onDemand, Spot = LoadInstances()
	region = CheapestRegion(onDemand, Spot)
	return jsonify({'cheapestregion':region})

@app.route('/instance/spread')
def InstanceSpread():
	onDemand, Spot = LoadInstances()
	spread = PriceByInstanceType(onDemand, Spot)
	return jsonify({'spread': spread})


#hit the amazon APIs and converts the return ondemand and spot listings to a json object
def LoadInstances():
	onDemandResponse = urlopen("http://a0.awsstatic.com/pricing/1/ec2/linux-od.min.js")
	onDemandJSONP = onDemandResponse.read()
	onDemandJSObj = UnwrapJSONP(onDemandJSONP)
	onDemandJSON = convertKeysToJSON(onDemandJSObj)	
	onDemand = loads(onDemandJSON)

	
	SpotResponse = urlopen("http://spot-price.s3.amazonaws.com/spot.js")	
	SpotResponseHTML = SpotResponse.read()
	SpotJSON = UnwrapJSONP(SpotResponseHTML)
	SpotJSON = SpotJSON.replace('"vers": 0.01,','').replace(')', '')	
	Spot = loads(SpotJSON)

	return onDemand, Spot


#returns a list of spreads by instance and region
def PriceByInstanceType(onDemand, spot):
	Regions = {}
	
	#build an object that contains all the prices for each size in each instance in each region
	ParseInstanceType(onDemand, Regions, 'OnDemandPrice')
	ParseInstanceType(spot, Regions, 'SpotPrice')		
	
	#if both an ondemand and spot price exist for a size add the difference between the two, to the list
	result = []
	for regionKey, region in Regions.items():
		for instanceKey, instance in region.items():
			for sizeKey, size in instance.items():
				if 'OnDemandPrice' in size and 'SpotPrice' in size:
					spread = float(size['OnDemandPrice']) - float(size['SpotPrice'])
					result.append({'Region':regionKey, 'Instance': instanceKey, 'Size': sizeKey, 'Spread': spread})
	return result


def ParseInstanceType(obj, Regions, name):
	for region in obj['config']['regions']:
		if region['region'] not in Regions:
			Regions[region['region']] = {}
		for instanceTypes in region['instanceTypes']:
			if instanceTypes['type'] not in Regions[region['region']]:
				Regions[region['region']][instanceTypes['type']] = {} 
			for sizes in instanceTypes['sizes']:
				if sizes['size'] not in Regions[region['region']][instanceTypes['type']]:	
					 Regions[region['region']][instanceTypes['type']][sizes['size']] = {}
				Regions[region['region']][instanceTypes['type']][sizes['size']][name] = sizes['valueColumns'][0]['prices']['USD']



#returns a list of the average vCPU size in each instance for all regions, sorted by lowest price
def vCPUInfo(onDemand, spot):
	PricePervCPU = [] 
	vCPU = {}
	counted = 0
	#For the on demand prices, average all sizes in all instances and add them to the list
	for region in onDemand['config']['regions']:
		for instancetypes in region['instanceTypes']:
			instanceTotalvCPU = 0
			for sizes in instancetypes['sizes']:
				instanceTotalvCPU += float(sizes['valueColumns'][0]['prices']['USD'])/float(sizes['vCPU'])
				#create a dictionary of sizes and how many CPUs they have
				vCPU[sizes['size']] = sizes['vCPU']
			avg = instanceTotalvCPU/len(sizes)	
			PricePervCPU.append({'region':region['region'], 'instance': instancetypes['type'],'instance_avg': avg,'pricetype': 'od'})

	#spot listings do not contain cpu info	so use the vCPU dict created from the ondemand listings.
	#not all sizes in the spot listings are available in the ondemand dict so discard those sizes that arent
	for region in spot['config']['regions']:
		for instancetypes in region['instanceTypes']:
			instanceTotalvCPU = 0
			counted = 0
			for size in instancetypes['sizes']:
				if size['size'] in vCPU and size['valueColumns'][0]['prices']['USD'] != 'N/A*':			
					instanceTotalvCPU += float(size['valueColumns'][0]['prices']['USD'])/float(vCPU[size['size']])
					counted += 1
			if  counted > 0:
				avg = float(instanceTotalvCPU)/float(counted)
				PricePervCPU.append({'region':region['region'], 'instance': instancetypes['type'],'instance_avg': avg,'pricetype': 'spot'})
	#sort by the avg price
	PricePervCPU = sorted(PricePervCPU, key = lambda k: k['instance_avg'])
	return PricePervCPU

#returns a dictionary of the average instance price in a region
def CheapestRegion(onDemand, Spot):

	Regions = {};
	AddRegionAvgToDict(onDemand, Regions)
	AddRegionAvgToDict(Spot, Regions)

	return min(Regions, key = Regions.get)


def AddRegionAvgToDict(data, dic):
	#for all regions
	for region in data['config']['regions']:
		regionTotalPrice = 0
		#for all instance types
		for instancetypes in region['instanceTypes']:
			instanceTotalPrice = 0
			#sum all Size prices if they are valid
			for sizes in instancetypes['sizes']:
				if sizes['valueColumns'][0]['prices']['USD'] != 'N/A*':
					instanceTotalPrice += float(sizes['valueColumns'][0]['prices']['USD'])
			#avg the sum of Size prices for the Instance
			instanceAverage = instanceTotalPrice/len(instancetypes['sizes'])	
			#add that instanceAverage to the Regions total
			regionTotalPrice += instanceAverage	
		#average all instances in a Region
		avg = float(regionTotalPrice)/len(region['instanceTypes'])
		#if the region exists in the dictionary already then average the old and new value
		if region['region'] in dic:
			dic[region['region']] = (dic[region['region']] + avg) / 2.0
		else:
			dic[region['region']] = avg


def UnwrapJSONP(JSONP):
	throwAwayString, mod = JSONP.split("callback(",1)	
	return mod.replace(');', '')


def convertKeysToJSON(javaScriptString):
	javaScriptString = javaScriptString.replace('vers:0.01,','')
	javaScriptString = javaScriptString.replace('config','"config"')
	javaScriptString = javaScriptString.replace('rate:','"rate":')
	javaScriptString = javaScriptString.replace('valueColumns:','"valueColumns":')
	javaScriptString = javaScriptString.replace('name:','"name":')
	javaScriptString = javaScriptString.replace('prices:','"prices":')
	javaScriptString = javaScriptString.replace('USD:','"USD":')
	javaScriptString = javaScriptString.replace('currencies:','"currencies":')
	javaScriptString = javaScriptString.replace('regions:','"regions":')
	javaScriptString = javaScriptString.replace('region:','"region":')
	javaScriptString = javaScriptString.replace('instanceTypes:','"instanceTypes":')
	javaScriptString = javaScriptString.replace('type:','"type":')
	javaScriptString = javaScriptString.replace('sizes:','"sizes":')
	javaScriptString = javaScriptString.replace('size:','"size":')
	javaScriptString = javaScriptString.replace('vCPU:','"vCPU":')
	javaScriptString = javaScriptString.replace('ECU:','"ECU":')
	javaScriptString = javaScriptString.replace('memoryGiB:','"memoryGiB":')
	javaScriptString = javaScriptString.replace('storageGB:','"storageGB":')
	return javaScriptString

if __name__ == "__main__":
	app.run(debug=True)

	
