/*
x * ExcaliburProcessPlugin.h
 *
 *  Created on: 6 Jun 2016
 *      Author: gnx91527
 */

#ifndef TOOLS_FILEWRITER_EXCALIBURREORDERPLUGIN_H_
#define TOOLS_FILEWRITER_EXCALIBURREORDERPLUGIN_H_

#include <log4cxx/logger.h>
#include <log4cxx/basicconfigurator.h>
#include <log4cxx/propertyconfigurator.h>
#include <log4cxx/helpers/exception.h>
#include <vector>
using namespace log4cxx;
using namespace log4cxx::helpers;


#include "FrameProcessorPlugin.h"
#include "ExcaliburDefinitions.h"
#include "ClassLoader.h"
#include "DataBlockFrame.h"

#define FEM_PIXELS_PER_CHIP_X 256
#define FEM_PIXELS_PER_CHIP_Y 256
#define FEM_CHIPS_PER_BLOCK_X 4
#define FEM_BLOCKS_PER_STRIPE_X 2
#define FEM_CHIPS_PER_STRIPE_X 8
#define FEM_CHIPS_PER_STRIPE_Y 1
#define FEM_STRIPES_PER_MODULE 2
#define FEM_STRIPES_PER_IMAGE 6
#define FEM_CHIP_GAP_PIXELS_X 3
#define FEM_CHIP_GAP_PIXELS_Y_LARGE 125
#define FEM_CHIP_GAP_PIXELS_Y_SMALL 3
#define FEM_PIXELS_PER_STRIPE_X ((FEM_PIXELS_PER_CHIP_X+FEM_CHIP_GAP_PIXELS_X)*FEM_CHIPS_PER_STRIPE_X-FEM_CHIP_GAP_PIXELS_X)
#define FEM_TOTAL_PIXELS_Y (FEM_PIXELS_PER_CHIP_Y*FEM_CHIPS_PER_STRIPE_Y*FEM_STRIPES_PER_IMAGE +\
                (FEM_STRIPES_PER_IMAGE/2-1)*FEM_CHIP_GAP_PIXELS_Y_LARGE +\
                (FEM_STRIPES_PER_IMAGE/2)*FEM_CHIP_GAP_PIXELS_Y_SMALL)
// #define FEM_TOTAL_PIXELS_X FEM_PIXELS_PER_STRIPE_X
#define FEM_TOTAL_PIXELS_X (FEM_PIXELS_PER_CHIP_X*FEM_CHIPS_PER_STRIPE_X)
#define FEM_TOTAL_PIXELS (FEM_TOTAL_PIXELS_X * FEM_PIXELS_PER_CHIP_Y)

#define FEM_PIXELS_IN_GROUP_6BIT 4
#define FEM_PIXELS_IN_GROUP_12BIT 4
#define FEM_PIXELS_PER_WORD_PAIR_1BIT 12
#define FEM_SUPERCOLUMNS_PER_CHIP 8
#define FEM_PIXELS_PER_SUPERCOLUMN_X (FEM_PIXELS_PER_CHIP_X / FEM_SUPERCOLUMNS_PER_CHIP)
#define FEM_SUPERCOLUMNS_PER_BLOCK_X (FEM_SUPERCOLUMNS_PER_CHIP * FEM_CHIPS_PER_BLOCK_X)

namespace FrameProcessor
{

  /** Processing of Excalibur Frame objects.
   *
   * The ExcaliburProcessPlugin class is currently responsible for receiving a raw data
   * Frame object and reordering the data into valid Excalibur frames according to the selected
   * bit depth.
   */
  class ExcaliburProcessPlugin : public FrameProcessorPlugin
  {
  public:
    ExcaliburProcessPlugin();
    virtual ~ExcaliburProcessPlugin();
    
    int get_version_major();
    int get_version_minor();
    int get_version_patch();
    std::string get_version_short();
    std::string get_version_long();

    void configure(OdinData::IpcMessage& config, OdinData::IpcMessage& reply);
    void requestConfiguration(OdinData::IpcMessage& reply);
    void status(OdinData::IpcMessage& status);
    bool reset_statistics(void);

  private:
    /** Configuration constant for asic counter depth **/
    static const std::string CONFIG_ASIC_COUNTER_DEPTH;
    /** Configuration constant for image width **/
    static const std::string CONFIG_IMAGE_WIDTH;
    /** Configuration constant for image height **/
    static const std::string CONFIG_IMAGE_HEIGHT;
    /** Configuration constant for reset of 24bit image counter **/
    static const std::string CONFIG_RESET_24_BIT;

    void process_lost_packets(boost::shared_ptr<Frame>& frame);
    boost::shared_ptr<Frame> create_data_frame(const std::string &dataset_name,
      const long long frame_number);
    void process_frame(boost::shared_ptr<Frame> frame);
    void reorder_1bit_stripe(unsigned int* in, unsigned char* out, bool stripe_is_even);
    void reorder_6bit_stripe(unsigned char* in, unsigned char* out, bool stripe_is_even);
    void reorder_12bit_stripe(unsigned short* in, unsigned short* out, bool stripe_is_even);
    void reorder_24bit_stripe(unsigned short* in_c0, unsigned short* in_c1, unsigned int* out,
        bool stripe_is_even);
    std::size_t reordered_image_size(Excalibur::AsicCounterBitDepth asic_counter_depth_);

    /** Pointer to logger **/
    LoggerPtr logger_;
    /** Bit depth of the incoming frames **/
    Excalibur::AsicCounterBitDepth asic_counter_bit_depth_;
    /** Bit depth string for reporting in config and status replies **/
    std::string asic_counter_bit_depth_str_;
    /** Image width **/
    int image_width_;
    /** Image height **/
    int image_height_;
    /** Image pixel count **/
    int image_pixels_;
    /** Packet loss counter **/
    int packets_lost_;
    std::vector<int> fem_packets_lost_;
    /** Number of FEMS in last frame **/
    int number_of_fems_;
  };

  /**
   * Registration of this plugin through the ClassLoader.  This macro
   * registers the class without needing to worry about name mangling
   */
  REGISTER(FrameProcessorPlugin, ExcaliburProcessPlugin, "ExcaliburProcessPlugin");

} /* namespace FrameProcessor */

#endif /* TOOLS_FILEWRITER_EXCALIBURREORDERPLUGIN_H_ */
