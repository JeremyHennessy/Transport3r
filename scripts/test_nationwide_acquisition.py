import json,pathlib,tempfile,unittest
from unittest.mock import patch
import nationwide_acquisition as acquisition


class NationwideResume(unittest.TestCase):
    def test_resume_reuses_verified_sources_and_only_acquires_missing(self):
        sources=[{'id':'aaaa-1111','name':'one','family':'test'},{'id':'bbbb-2222','name':'two','family':'test'}]
        with tempfile.TemporaryDirectory() as root:
            project=pathlib.Path(root,'project');(project/'data').mkdir(parents=True);(project/'data/fmcsa_sources.json').write_text(json.dumps(sources))
            collection=pathlib.Path(root,'collection');collection.mkdir();(collection/'requested-sources.json').write_text(json.dumps(sources))
            (collection/'run.json').write_text(json.dumps({'schema_version':7,'snapshot_id':'collection','started_at':'2026-10-23T00:00:00Z','acquisition_kind':'NATIONWIDE_SOURCE_COLLECTION','historical_reconstruction':False}))
            reused={'id':'aaaa-1111','status':'COMPLETE','cut':'aaaa-1111/old','rows':1,'bytes':10,'attempts':[{'status':'COMPLETE','reused':True}]}
            calls=[]
            def accepted(folder,source):return reused if source['id']=='aaaa-1111' else None
            def acquire(selected,folder,compression=None):
                calls.append((selected[0]['id'],compression));cut=pathlib.Path(folder,'new');cut.mkdir(parents=True)
                return cut,{'status':'COMPLETE','datasets':[{'row_count':2,'bytes':20}]}
            with patch.object(acquisition,'ROOT',project),patch.object(acquisition,'accepted',side_effect=accepted),patch.object(acquisition,'acquire',side_effect=acquire):
                result=acquisition.run(pathlib.Path(root,'unused'),workers=1,collection=collection)
            self.assertEqual(calls,[('bbbb-2222','gzip')]);self.assertEqual(result['status'],'COMPLETE')
            self.assertEqual([item['id'] for item in result['sources']],['aaaa-1111','bbbb-2222'])
            self.assertTrue((collection/'manifest.json').is_file())


if __name__=='__main__':unittest.main()
